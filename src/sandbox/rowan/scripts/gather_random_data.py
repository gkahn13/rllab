import os, argparse

from gcg.data.logger import logger
from gcg.envs.env_utils import create_env
from gcg.sampler.sampler import Sampler
from gcg.data import mypickle

class DummyPolicy(object):
    @property
    def N(self):
        return 1

    @property
    def gamma(self):
        return 1    

    @property
    def obs_history_len(self):
        return 1

    def get_actions(self, **kwargs):
        pass

    def reset_get_action(self):
        pass

class GatherRandomData(object):
    def __init__(self, env, steps, save_file):
        self._env = env
        self._steps = steps
        self._save_file = save_file

        self._sampler = Sampler(
                            policy=DummyPolicy(),
                            env=self._env,
                            n_envs=1,
                            replay_pool_size=steps,
                            max_path_length=self._env.horizon,
                            sampling_method='uniform',
                            save_rollouts=True,
                            save_rollouts_observations=True,
                            save_env_infos=True)

    def run(self):
        self._sampler.reset()
        step = 0
        while step < self._steps:
            self._sampler.step(step, take_random_actions=True)
            step += 1

        rollouts = self._sampler.get_recent_paths()
        mypickle.dump({'rollouts': rollouts}, self._save_file)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('env', type=str, choices=('SquareClutteredEnv', 'SquareClutteredHoldoutEnv',))
    parser.add_argument('steps', type=int)
    args = parser.parse_args()

    logger.setup(display_name='gather_random_data', log_path='/tmp/log.txt', lvl='debug')

    if args.env == 'SquareClutteredEnv':
        env = create_env("SquareClutteredEnv(params={'hfov': 120, 'do_back_up': True, 'collision_reward_only': True, 'collision_reward': -1, 'speed_limits': [2., 2.]})")
    elif args.env == 'SquareClutteredHoldoutEnv':
        env = create_env("SquareClutteredHoldoutEnv(params={'hfov': 120, 'do_back_up': True, 'collision_reward_only': True, 'collision_reward': -1, 'speed_limits': [2., 2.]})")
    else:
        raise NotImplementedError

    curr_dir = os.path.realpath(os.path.dirname(__file__))
    data_dir = os.path.join(curr_dir[:curr_dir.find('gcg/src')], 'gcg/data')
    assert (os.path.exists(data_dir))
    fname = '{0}_random{1:d}.pkl'.format(args.env, args.steps)
    save_dir = os.path.join(data_dir, 'bnn/datasets', os.path.splitext(fname)[0])
    os.makedirs(save_dir, exist_ok=True)
    savefile = os.path.join(save_dir, fname)

    grd = GatherRandomData(env, args.steps, savefile)
    grd.run()

