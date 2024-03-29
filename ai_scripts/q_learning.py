import os
import json
import copy

import numpy as np
import networkx as nx

from helper_scripts.sim_helpers import find_path_len, get_path_mod, calc_matrix_stats
from helper_scripts.os_helpers import create_dir
from arg_scripts.ai_args import empty_q_props


# TODO: This script is no longer supported
class QLearning:
    """
    Contains methods related to the q-learning algorithm.
    """

    def __init__(self, engine_props: dict):
        self.q_props = copy.deepcopy(empty_q_props)
        self.engine_props = engine_props

        self.num_nodes = None
        self.k_paths = None
        self.source = None
        self.destination = None

        self.chosen_path = None
        self.chosen_bw = None
        self.core_index = None

        self.routing_obj = None
        self.curr_episode = None
        self.paths_list = None
        self.path_index = None

    @staticmethod
    def set_seed(seed: int):
        """
        Sets the seed for the random generation.
        :param seed: The input seed.
        """
        np.random.seed(seed)

    def decay_epsilon(self, amount: float):
        """
        Decays the epsilon parameter.
        :param amount: The amount to decay by.
        """
        self.q_props['epsilon'] -= amount
        if self.curr_episode == 0:
            self.q_props['epsilon_list'].append(self.q_props['epsilon'])

        if self.q_props['epsilon'] < 0.0:
            raise ValueError(f"Epsilon should be greater than 0 but it is {self.q_props['epsilon']}")

    def _save_params(self, save_dir: str):
        params_dict = dict()
        for param_type, params_list in self.q_props['save_params_dict'].items():
            for curr_param in params_list:
                if param_type == 'engine_params_list':
                    params_dict[curr_param] = self.engine_props[curr_param]
                else:
                    params_dict[curr_param] = self.q_props[curr_param]

        param_fp = f"e{self.engine_props['erlang']}_params_c{self.engine_props['cores_per_link']}.json"
        param_fp = os.path.join(save_dir, param_fp)
        with open(param_fp, 'w', encoding='utf-8') as file_obj:
            json.dump(params_dict, file_obj)

    def save_model(self):
        """
        Saves the q-tables created and relevant parameter values.
        """
        date_time = os.path.join(self.engine_props['network'], self.engine_props['date'],
                                 self.engine_props['sim_start'])
        save_dir = os.path.join('data', 'ai', 'models', date_time)
        create_dir(file_path=save_dir)

        route_fp = f"e{self.engine_props['erlang']}_routes_c{self.engine_props['cores_per_link']}.npy"
        core_fp = f"e{self.engine_props['erlang']}_cores_c{self.engine_props['cores_per_link']}.npy"

        for curr_fp in (route_fp, core_fp):
            save_fp = os.path.join(os.getcwd(), save_dir, curr_fp)

            if curr_fp.split('_')[1] == 'routes':
                np.save(save_fp, 'routes_matrix')
            else:
                np.save(save_fp, self.q_props['cores_matrix'])

        self._save_params(save_dir=save_dir)

    def load_model(self):
        """
        Loads a previously trained model.
        """
        raise NotImplementedError

    def _calc_averages(self, stats_flag: str, episode: str):
        len_rewards = len(self.q_props['rewards_dict'][stats_flag]['rewards'][episode])
        if self.curr_episode == self.engine_props['max_iters'] - 1 and len_rewards == self.engine_props['num_requests']:
            rewards_dict = self.q_props['rewards_dict'][stats_flag]['rewards']
            errors_dict = self.q_props['errors_dict'][stats_flag]['errors']
            self.q_props['rewards_dict'][stats_flag] = calc_matrix_stats(input_dict=rewards_dict)
            self.q_props['errors_dict'][stats_flag] = calc_matrix_stats(input_dict=errors_dict)

    def _update_stats(self, reward: float, td_error: float, stats_flag: str):
        episode = str(self.curr_episode)

        if episode not in self.q_props['rewards_dict'][stats_flag]['rewards'].keys():
            self.q_props['rewards_dict'][stats_flag]['rewards'][episode] = [reward]
            self.q_props['errors_dict'][stats_flag]['errors'][episode] = [td_error]
            self.q_props['sum_rewards_dict'][episode] = reward
            self.q_props['sum_errors_dict'][episode] = td_error
        else:
            self.q_props['rewards_dict'][stats_flag]['rewards'][episode].append(reward)
            self.q_props['errors_dict'][stats_flag]['errors'][episode].append(td_error)
            self.q_props['sum_rewards_dict'][episode] += reward
            self.q_props['sum_errors_dict'][episode] += td_error

        self._calc_averages(stats_flag=stats_flag, episode=episode)

    def _update_routes_matrix(self, was_routed: bool):
        if was_routed:
            reward = 1.0
        else:
            reward = -10.0

        routes_matrix = self.q_props['routes_matrix'][self.source][self.destination][self.path_index]
        current_q = routes_matrix['q_value']
        max_future_q = self._get_max_future_q()
        delta = reward + self.engine_props['discount_factor'] * max_future_q
        td_error = current_q - (reward + self.engine_props['discount_factor'] * max_future_q)
        self._update_stats(reward=reward, stats_flag='routes_dict', td_error=td_error)

        new_q = ((1.0 - self.engine_props['learn_rate']) * current_q) + (self.engine_props['learn_rate'] * delta)

        self.q_props['routes_matrix'][self.source][self.destination][self.path_index]['q_value'] = new_q

    def _update_cores_matrix(self, was_routed: bool):
        if was_routed:
            reward = 1.0
        else:
            reward = -10.0

        q_cores_matrix = self.q_props['cores_matrix'][self.source][self.destination][self.path_index]
        current_q = q_cores_matrix[self.core_index]['q_value']
        # TODO: What to do with maximum future Q without spectrum assignment? Constant for now
        max_future_q = 1.0
        delta = reward + self.engine_props['discount_factor'] * max_future_q
        self._update_stats(reward=reward, stats_flag='cores_dict', td_error=delta)

        new_q_core = ((1.0 - self.engine_props['learn_rate']) * current_q) + (self.engine_props['learn_rate'] * delta)
        self.q_props['cores_matrix'][self.source][self.destination][self.path_index][self.core_index][
            'q_value'] = new_q_core

    def update_env(self, was_routed: bool):
        """
        Updates q-tables.

        :param was_routed: If the request was routed or blocked.
        """
        self._update_routes_matrix(was_routed=was_routed)
        self._update_cores_matrix(was_routed=was_routed)

    def _init_q_tables(self):
        for source in range(0, self.num_nodes):
            for destination in range(0, self.num_nodes):
                # A node cannot be attached to itself
                if source == destination:
                    continue

                shortest_paths = nx.shortest_simple_paths(G=self.engine_props['topology'], source=str(source),
                                                          target=str(destination), weight='length')
                for k, curr_path in enumerate(shortest_paths):
                    if k >= self.k_paths:
                        break
                    self.q_props['routes_matrix'][source, destination, k] = (curr_path, 0.0)

                    for core_action in range(self.engine_props['cores_per_link']):
                        self.q_props['cores_matrix'][source, destination, k, core_action] = (curr_path, core_action,
                                                                                             0.0)

    def setup_env(self):
        """
        Sets up the q-tables and relevant parameters.
        """
        self.q_props['epsilon'] = self.engine_props['epsilon_start']
        self.num_nodes = len(self.engine_props['topology_info']['nodes'].keys())
        self.k_paths = int(self.engine_props['k_paths'])

        route_types = [('path', 'O'), ('q_value', 'f8')]
        core_types = [('path', 'O'), ('core_action', 'i8'), ('q_value', 'f8')]

        self.q_props['routes_matrix'] = np.empty((self.num_nodes, self.num_nodes, self.k_paths), dtype=route_types)
        self.q_props['cores_matrix'] = np.empty((self.num_nodes, self.num_nodes, self.k_paths,
                                                 self.engine_props['cores_per_link']), dtype=core_types)

        self._init_q_tables()

    def _get_max_future_q(self):
        q_values = list()
        cores_matrix = self.q_props['cores_matrix'][self.source][self.destination][self.path_index]
        for core_index in range(self.engine_props['cores_per_link']):
            curr_q = cores_matrix[core_index]['q_value']
            q_values.append(curr_q)

        max_index = np.argmax(q_values)
        resp_value = cores_matrix[max_index]['q_value']
        return resp_value

    def _get_max_curr_q(self):
        q_values = list()
        for path_index in range(len(self.paths_list)):
            curr_q = self.q_props['routes_matrix'][self.source][self.destination][path_index]['q_value']
            q_values.append(curr_q)

        max_index = np.argmax(q_values)
        max_path = self.paths_list[max_index]
        return max_index, max_path

    def _update_route_props(self, sdn_props: dict, route_props: dict):
        route_props['paths_list'].append(self.chosen_path)
        path_len = find_path_len(path_list=self.chosen_path, topology=self.engine_props['topology'])
        chosen_bw = sdn_props['bandwidth']
        mod_format = get_path_mod(mods_dict=self.engine_props['mod_per_bw'][chosen_bw], path_len=path_len)
        route_props['mod_formats_list'].append([mod_format])
        route_props['weights_list'].append(path_len)

    def get_route(self, sdn_props: dict, route_props: dict):
        """
        Assigns a route to an incoming request.

        :param sdn_props: Holds SDN controller information.
        :param route_props: Holds Routing information.
        """
        random_float = np.round(np.random.uniform(0, 1), decimals=1)
        self.source = int(sdn_props['source'])
        self.destination = int(sdn_props['destination'])
        self.paths_list = self.q_props['routes_matrix'][self.source][self.destination]['path']

        if self.paths_list.ndim != 1:
            self.paths_list = self.paths_list[:, 0]

        if random_float < self.q_props['epsilon']:
            self.path_index = np.random.choice(self.k_paths)

            if self.path_index == 1 and self.k_paths == 1:
                self.path_index = 0
            self.chosen_path = self.paths_list[self.path_index]
        else:
            self.path_index, self.chosen_path = self._get_max_curr_q()

        if len(self.chosen_path) == 0:
            raise ValueError('The chosen path can not be None')

        self._update_route_props(sdn_props=sdn_props, route_props=route_props)

    def get_core(self, spectrum_props: dict):
        """
        Assigns a core to an incoming network request.

        :param spectrum_props: Holds spectrum assignment information.
        """
        random_float = np.round(np.random.uniform(0, 1), decimals=1)

        if random_float < self.q_props['epsilon']:
            self.core_index = np.random.randint(0, self.engine_props['cores_per_link'])
        else:
            q_values = self.q_props['cores_matrix'][self.source][self.destination][self.path_index]['q_value']
            self.core_index = np.argmax(q_values)

        spectrum_props['forced_core'] = self.core_index
