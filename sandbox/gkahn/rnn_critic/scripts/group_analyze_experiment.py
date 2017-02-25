import os
import itertools

import numpy as np
import scipy
import matplotlib.pyplot as plt
from matplotlib import ticker

from sandbox.gkahn.rnn_critic.envs.chain_env import ChainEnv

from analyze_experiment import AnalyzeRNNCritic

##################
### Processing ###
##################

def flatten_list(l):
    return [val for sublist in l for val in sublist]

class DataAverageInterpolation(object):
    def __init__(self):
        self.xs = []
        self.ys = []
        self.fs = []

    def add_data(self, x, y):
        self.xs.append(x)
        self.ys.append(y)
        self.fs.append(scipy.interpolate.interp1d(x, y))

    def eval(self, x):
        ys = [f(x) for f in self.fs]
        return np.array(np.mean(ys, axis=0)), np.array(np.std(ys, axis=0))

################
### Analysis ###
################

class PlotAnalyzeRNNCritic(object):
    def __init__(self, save_folder, name, analyze_groups):
        """
        :param analyze_groups: [[AnalyzeRNNCritic, AnalyzeRNNCritic, ...], [AnalyzeRNNCritic, AnalyzeRNNCritic, ...]]
        """
        self._save_folder = save_folder
        self._name = name
        self._analyze_groups = analyze_groups

        env = analyze_groups[0][0].env_itrs[0]
        while hasattr(env, 'wrapped_env'):
            env = env.wrapped_env
        self._env_type = type(env)

    #############
    ### Files ###
    #############

    @property
    def _folder(self):
        folder = os.path.join(self._save_folder, self._name)
        if not os.path.exists(folder):
            os.mkdir(folder)
        return folder

    @property
    def _analyze_img_file(self):
        return os.path.join(self._folder, '{0}_analyze.png'.format(self._name))

    ################
    ### Plotting ###
    ################

    def _plot_analyze(self):
        if self._env_type == ChainEnv:
            self._plot_analyze_ChainEnv()
        else:
            pass

    def _plot_analyze_ChainEnv(self):
        f, axes = plt.subplots(1+len(self._analyze_groups), 1, figsize=(15, 5*len(self._analyze_groups)), sharex=True)

        ### plot training cost
        ax = axes[0]
        for analyze_group in self._analyze_groups:
            data_interp = DataAverageInterpolation()
            for analyze in analyze_group:
                steps = analyze.progress['Step'][1:]
                costs = analyze.progress['Cost'][1:]
                data_interp.add_data(steps, costs)

            steps = np.r_[min(flatten_list(data_interp.xs)):max(flatten_list(data_interp.xs)):0.01]
            costs_mean, costs_std = data_interp.eval(steps)

            ax.plot(steps, costs_mean, color=analyze.plot['color'], label=analyze.plot['label'])
            ax.fill_between(steps, costs_mean - costs_std, costs_mean + costs_std,
                            color=analyze.plot['color'], alpha=0.4)
        ax.set_ylabel('Training cost')
        ax.legend(loc='upper right')

        ### plot training rollout length vs step
        for ax, analyze_group in zip(axes[1:], self._analyze_groups):
            data_interp = DataAverageInterpolation()
            min_step = max_step = None
            for analyze in analyze_group:
                rollouts = list(itertools.chain(*analyze.train_rollouts_itrs))
                rollout_lens = [len(r['observations']) for r in rollouts]
                steps = [r['steps'][-1] for r in rollouts]
                def moving_avg_std(idxs, data, window):
                    means, stds = [], []
                    for i in range(window, len(data)):
                        means.append(np.mean(data[i - window:i]))
                        stds.append(np.std(data[i - window:i]))
                    return idxs[window:], np.asarray(means), np.asarray(stds)
                moving_steps, moving_rollout_lens, _ = moving_avg_std(steps, rollout_lens, 5)
                data_interp.add_data(moving_steps, moving_rollout_lens)
                if min_step is None:
                    min_step = moving_steps[0]
                if max_step is None:
                    max_step = moving_steps[-1]
                min_step = max(min_step, moving_steps[0])
                max_step = min(max_step, moving_steps[-1])
            steps = np.r_[min_step:max_step:0.01]
            lens_mean, lens_std = data_interp.eval(steps)

            ax.plot(steps, lens_mean, color=analyze.plot['color'], label=analyze.plot['label'])
            ax.fill_between(steps, lens_mean - lens_std, lens_mean + lens_std,
                            color=analyze.plot['color'], alpha=0.4)
            ax.vlines(analyze.params['alg']['learn_after_n_steps'], 0, ax.get_ylim()[1], colors='k', linestyles='dashed')
            ax.hlines(analyze.env_itrs[0].spec.observation_space.n, steps[0], steps[-1], colors='k', linestyles='dashed')
            ax.set_ylabel('Rollout length')

        ### for all plots
        ax.set_xlabel('Steps')
        xfmt = ticker.ScalarFormatter()
        xfmt.set_powerlimits((0, 0))
        ax.xaxis.set_major_formatter(xfmt)

        f.savefig(self._analyze_img_file, bbox_inches='tight')
        plt.close(f)

    ###########
    ### Run ###
    ###########

    def run(self):
        self._plot_analyze()

if __name__ == '__main__':
    SAVE_FOLDER = '/home/gkahn/code/rllab/data/local/rnn-critic/'

    analyze_groups = []
    ### H = 1
    analyze_group = []
    for i in range(50, 55):
        analyze_group.append(AnalyzeRNNCritic(os.path.join(SAVE_FOLDER, 'exp{0}'.format(i)),
                                              plot={
                                                  'label': 'H = 1',
                                                  'color': 'r'
                                              }))
    analyze_groups.append(analyze_group)
    ### H = 2
    analyze_group = []
    for i in range(55, 60):
        analyze_group.append(AnalyzeRNNCritic(os.path.join(SAVE_FOLDER, 'exp{0}'.format(i)),
                                              plot={
                                                  'label': 'H = 2',
                                                  'color': 'g'
                                              }))
    analyze_groups.append(analyze_group)
    ### H = 3
    analyze_group = []
    for i in range(60, 65):
        analyze_group.append(AnalyzeRNNCritic(os.path.join(SAVE_FOLDER, 'exp{0}'.format(i)),
                                              plot={
                                                  'label': 'H = 3',
                                                  'color': 'b'
                                              }))
    analyze_groups.append(analyze_group)
    ### H = 4
    analyze_group = []
    for i in range(65, 70):
        analyze_group.append(AnalyzeRNNCritic(os.path.join(SAVE_FOLDER, 'exp{0}'.format(i)),
                                              plot={
                                                  'label': 'H = 4',
                                                  'color': 'y'
                                              }))
    analyze_groups.append(analyze_group)
    ### H = 5
    analyze_group = []
    for i in range(70, 75):
        analyze_group.append(AnalyzeRNNCritic(os.path.join(SAVE_FOLDER, 'exp{0}'.format(i)),
                                              plot={
                                                  'label': 'H = 5',
                                                  'color': 'c'
                                              }))
    analyze_groups.append(analyze_group)

    plotter = PlotAnalyzeRNNCritic(os.path.join(SAVE_FOLDER, 'analyze'), 'chain', analyze_groups)
    plotter.run()
