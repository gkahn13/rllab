import numpy as np

from rllab.core.serializable import Serializable
from rllab.exploration_strategies.base import ExplorationStrategy
from sandbox.rocky.tf.spaces.box import Box
from sandbox.gkahn.rnn_critic.utils import schedules

class GaussianStrategy(ExplorationStrategy, Serializable):
    """
    Add gaussian noise
    """
    def __init__(self, env_spec, endpoints, outside_value):
        assert isinstance(env_spec.action_space, Box)
        Serializable.quick_init(self, locals())
        self._env_spec = env_spec
        self._schedule = schedules.PiecewiseSchedule(endpoints=endpoints, outside_value=outside_value)

    def get_action(self, t, observation, policy, **kwargs):
        action, _ = policy.get_action(observation)
        return np.clip(action + np.random.normal(size=len(action)) * self._schedule.value(t),
                       self._env_spec.action_space.low, self._env_spec.action_space.high)