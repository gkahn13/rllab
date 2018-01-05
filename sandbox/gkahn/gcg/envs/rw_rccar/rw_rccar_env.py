import os

import numpy as np
#import cv2
from PIL import Image
from io import BytesIO

from rllab.envs.base import Env
from rllab.spaces.box import Box
from rllab.misc import logger as rllab_logger

from sandbox.gkahn.gcg.utils import logger

import rospy
import rosbag
import std_msgs.msg
import geometry_msgs.msg
import sensor_msgs.msg

class RolloutRosbag:

    def __init__(self):
        self._rosbag = None
        self._last_write = None

    @property
    def _rosbag_dir(self):
        dir = os.path.join(rllab_logger.get_snapshot_dir(), 'rosbags')
        if not os.path.exists(dir):
            os.mkdir(dir)
        return dir

    def _rosbag_name(self, num):
        return os.path.join(self._rosbag_dir, 'rosbag{0:04d}.bag'.format(num))

    def open(self):
        assert (self._rosbag is None)

        bag_num = 0
        while os.path.exists(self._rosbag_name(bag_num)):
            bag_num += 1

        self._rosbag = rosbag.Bag(self._rosbag_name(bag_num), 'w')
        self._last_write = rospy.Time.now()

    def write(self, topic, msg, stamp):
        assert (self._rosbag is not None)

        if msg is not None and stamp is not None:
            if stamp > self._last_write:
                self._rosbag.write(topic, msg)
        else:
            logger.warn('Topic {0} not received'.format(topic))

    def write_all(self, topics, msg_dict, stamp_dict):
        for topic in topics:
            self.write(topic, msg_dict.get(topic), stamp_dict.get(topic))

    def close(self):
        assert (self._rosbag is not None)

        self._rosbag.close()
        self._rosbag = None
        self._last_write = None


class RWrccarEnv:

    def __init__(self, params={}):
        params.setdefault('dt', 0.25)
        params.setdefault('horizon', int(5. * 60. / params['dt'])) # 5 minutes worth
        params.setdefault('ros_namespace', '/rccar/')
        params.setdefault('obs_shape', (64, 36))
        params.setdefault('steer_limits', [-1., 1.])
        params.setdefault('speed_limits', [0.2, 0.2])
        params.setdefault('backup_motor', -0.22)
        params.setdefault('backup_duration', 1.6)
        params.setdefault('backup_steer_range', (-0.5, 0.5))

        self._collision_reward = params['collision_reward']
        self._collision_reward_only = params['collision_reward_only']

        self._dt = params['dt']
        self.horizon = params['horizon']

        self.action_space = Box(low=np.array([params['steer_limits'][0], params['speed_limits'][0]]),
                                high=np.array([params['steer_limits'][1], params['speed_limits'][1]]))
        self.observation_space = Box(low=0, high=255, shape=params['obs_shape'])

        self._last_step_time = None
        self._is_collision = False
        self._backup_motor = params['backup_motor']
        self._backup_duration = params['backup_duration']
        self._backup_steer_range = params['backup_steer_range']

        ### ROS
        rospy.init_node('RWrccarEnv', anonymous=True)
        rospy.sleep(1)

        self._ros_namespace = params['ros_namespace']
        self._ros_topics_and_types = dict([
            ('camera/image_raw/compressed', sensor_msgs.msg.CompressedImage),
            ('mode', std_msgs.msg.Int32),
            ('steer', std_msgs.msg.Float32),
            ('motor', std_msgs.msg.Float32),
            ('battery/a', std_msgs.msg.Float32),
            ('battery/b', std_msgs.msg.Float32),
            ('battery/low', std_msgs.msg.Int32),
            ('encoder/left', std_msgs.msg.Float32),
            ('encoder/right', std_msgs.msg.Float32),
            ('encoder/both', std_msgs.msg.Float32),
            ('orientation/quat', geometry_msgs.msg.Quaternion),
            ('orientation/rpy', geometry_msgs.msg.Vector3),
            ('imu', geometry_msgs.msg.Accel),
            ('collision/all', std_msgs.msg.Int32),
            ('collision/flip', std_msgs.msg.Int32),
            ('collision/jolt', std_msgs.msg.Int32),
            ('collision/stuck', std_msgs.msg.Int32),
            ('collision/bumper', std_msgs.msg.Int32),
            ('cmd/steer', std_msgs.msg.Float32),
            ('cmd/motor', std_msgs.msg.Float32),
            ('cmd/vel', std_msgs.msg.Float32)
        ])
        self._ros_msgs = dict()
        self._ros_msg_times = dict()
        for topic, type in self._ros_topics_and_types.items():
            rospy.Subscriber(self._ros_namespace + topic, type, self._ros_callback, (topic,))
        self._ros_steer_pub = rospy.Publisher(self._ros_namespace + 'cmd/steer', std_msgs.msg.Float32, queue_size=10)
        self._ros_vel_pub = rospy.Publisher(self._ros_namespace + 'cmd/vel', std_msgs.msg.Float32, queue_size=10)
        self._ros_motor_pub = rospy.Publisher(self._ros_namespace + 'cmd/motor', std_msgs.msg.Float32, queue_size=10)
        self._ros_pid_enable_pub = rospy.Publisher(self._ros_namespace + 'pid/enable', std_msgs.msg.Empty, queue_size=10)
        self._ros_pid_disable_pub = rospy.Publisher(self._ros_namespace + 'pid/disable', std_msgs.msg.Empty, queue_size=10)

        self._ros_rolloutbag = RolloutRosbag()
        self._ros_rolloutbag.open()

        rospy.sleep(1)

    def _get_observation(self):
        ### ROS --> np
        msg = self._ros_msgs['camera/image_raw/compressed']

        # .03 seconds to do all below

        recon_pil_jpg = BytesIO(msg.data)
        recon_pil_arr = Image.open(recon_pil_jpg)
        
        grayscale = recon_pil_arr.convert('L')
        grayscale_resized = grayscale.resize(self.observation_space.shape, Image.ANTIALIAS)
        im = np.array(grayscale_resized)
        
        return im

    def _get_speed(self):
        return self._ros_msgs['encoder/both'].data

    def _get_reward(self):
        reward = self._collision_reward if self._is_collision else self._get_speed()
        return reward

    def _get_done(self):
        return self._is_collision

    def _set_steer(self, steer):
        self._ros_steer_pub.publish(std_msgs.msg.Float32(steer))

    def _set_vel(self, vel):
        if self._is_collision and vel > 0:
            vel = 0.
        self._ros_vel_pub.publish(std_msgs.msg.Float32(vel))

    def _set_motor(self, motor, duration):
        self._ros_pid_disable_pub.publish(std_msgs.msg.Empty())
        self._ros_motor_pub.publish(std_msgs.msg.Float32(motor))
        rospy.sleep(duration)
        self._ros_motor_pub.publish(std_msgs.msg.Float32(0.))
        self._ros_pid_enable_pub.publish(std_msgs.msg.Empty())
        
    def step(self, action):
        assert (self._ros_is_good)

        lb, ub = self.action_space.bounds
        action = np.clip(action, lb, ub)

        cmd_steer, cmd_vel = action
        self._set_steer(cmd_steer)
        self._set_vel(cmd_vel)

        next_observation = self._get_observation()
        reward = self._get_reward()
        done = self._get_done()
        env_info = dict()

        self._ros_rolloutbag.write_all(self._ros_topics_and_types.keys(), self._ros_msgs, self._ros_msg_times)

        rospy.sleep(max(0., self._dt - (rospy.Time.now() - self._last_step_time).to_sec()))
        self._last_step_time = rospy.Time.now()

        return next_observation, reward, done, env_info

    def reset(self):
        assert (self._ros_is_good)

        if self._is_collision:
            logger.debug('Resetting (collision)')
        else:
            logger.debug('Resetting (no collision)')

        self._ros_rolloutbag.close()

        if self._ros_msgs['collision/flip'].data:
            logger.warn('Car has flipped, please unflip it to continue')
            while self._ros_msgs['collision/flip'].data:
                rospy.sleep(0.1)
            logger.warn('Car is now unflipped. Continuing...')
            rospy.sleep(1.)

        backup_steer = np.random.uniform(*self._backup_steer_range)
        self._set_steer(backup_steer)
        self._set_motor(self._backup_motor, self._backup_duration)
        self._set_steer(0.)
        self._set_vel(0.)

        rospy.sleep(0.5)

        self._last_step_time = rospy.Time.now()
        self._is_collision = False

        self._ros_rolloutbag.open()

        assert (self._ros_is_good)

        return self._get_observation()
        
    ###########
    ### ROS ###
    ###########

    def _ros_callback(self, msg, args):
        topic = args[0]
        self._ros_msgs[topic] = msg
        self._ros_msg_times[topic] = rospy.Time.now()

        if topic == 'collision/all':
            if msg.data == 1:
                self._is_collision = True

        #if 'collision' in topic and msg.data == 1 and 'all' not in topic:
        #    logger.debug(topic)

    @property
    def _ros_is_good(self):
        # check that all not commands are coming in at a continuous rate
        for topic in self._ros_topics_and_types.keys():
            if 'cmd' not in topic and 'collision' not in topic:
                elapsed = (rospy.Time.now() - self._ros_msg_times[topic]).to_sec()
                if elapsed > self._dt:
                    logger.debug('Topic {0} was received {1} seconds ago (dt is {2})'.format(topic, elapsed, self._dt))
                    return False

        # check if in python mode
        if self._ros_msgs.get('mode') is None or self._ros_msgs['mode'].data != 2:
            logger.debug('In mode {0}'.format(self._ros_msgs.get('mode')))
            return False

        # check if battery is low
        if self._ros_msgs.get('battery/low') is None or self._ros_msgs['battery/low'].data == 1:
            logger.debug('Low battery!')
            return False

        return True
