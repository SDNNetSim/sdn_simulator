# Standard library imports
import numpy as np
from typing import Dict

# Third-party library imports
import networkx as nx

# Local application imports
from sim_scripts.routing import Routing
from sim_scripts.spectrum_assignment import SpectrumAssignment
from useful_functions.sim_functions import get_path_mod, sort_dict_keys, find_path_len


class SDNController:
    """
    Handles spectrum allocation for a request in the simulation.
    """

    def __init__(self, req_id: int = None, net_spec_db: dict = None, topology: nx.Graph = None,
                 cores_per_link: int = None, path: list = None, sim_type: str = None, alloc_method: str = None,
                 source: int = None, destination: int = None, mod_per_bw: dict = None, chosen_bw: str = None,
                 max_slices: int = None, guard_slots: int = None):
        """
        Initializes the SDNController class.

        :param req_id: The ID of the request.
        :type req_id: int

        :param net_spec_db: The network's spectrum database.
        :type net_spec_db: dict

        :param topology: The network's topology.
        :type topology: nx.Graph

        :param cores_per_link: The amount of cores per link in the network.
        :type cores_per_link: int

        :param path: The path in the network to be allocated.
        :type path: list

        :param sim_type: The type of simulation, which handles various assumptions.
        :type sim_type: str

        :param alloc_method: The allocation policy for a request.
        :type alloc_method: str

        :param source: The source node of the request.
        :type source: int

        :param destination: The destination node of the request.
        :type destination: int

        :param mod_per_bw: Modulation formats for every bandwidth in the network.
        :type mod_per_bw: dict

        :param chosen_bw: The chosen bandwidth for this request.
        :type chosen_bw: str

        :param max_slices: The maximum number of slices allowed.
        :type max_slices: int

        :param guard_slots: The amount of slots to be allocated for the guard band.
        :type guard_slots: int
        """
        self.req_id = req_id
        self.net_spec_db = net_spec_db
        self.topology = topology
        self.cores_per_link = cores_per_link
        self.path = path
        self.sim_type = sim_type
        self.alloc_method = alloc_method

        self.source = source
        self.destination = destination
        self.mod_per_bw = mod_per_bw
        self.chosen_bw = chosen_bw
        self.max_slices = max_slices
        self.guard_slots = guard_slots

        # Determines if light slicing is limited to a single core or not
        self.single_core = False
        # The number of transponders used to allocate the request
        self.num_transponders = 1
        # Determines whether the block was due to distance or congestion
        self.dist_block = False

    def release(self):
        """
        Handles a departure event. Finds where a request was previously allocated and releases it by setting the indexes
        to all zeros.

        :return: None
        """
        for src, dest in zip(self.path, self.path[1:]):
            src_dest = (src, dest)
            dest_src = (dest, src)

            for core_num in range(self.cores_per_link):
                core_arr = self.net_spec_db[src_dest]['cores_matrix'][core_num]
                req_indexes = np.where(core_arr == self.req_id)
                guard_bands = np.where(core_arr == (self.req_id * -1))

                for index in req_indexes:
                    self.net_spec_db[src_dest]['cores_matrix'][core_num][index] = 0
                    self.net_spec_db[dest_src]['cores_matrix'][core_num][index] = 0
                for gb_index in guard_bands:
                    self.net_spec_db[src_dest]['cores_matrix'][core_num][gb_index] = 0
                    self.net_spec_db[dest_src]['cores_matrix'][core_num][gb_index] = 0

    def allocate(self, start_slot: int, end_slot: int, core_num: int):
        """
        Handles an arrival event. Sets the allocated spectral slots equal to the request ID, the request ID is negative
        for the guard band to differentiate which slots are guard bands for future SNR calculations.

        :param start_slot: The starting spectral slot to allocate the request
        :type start_slot: int

        :param end_slot: The ending spectral slot to allocate the request
        :type end_slot: int

        :param core_num: The desired core to allocate the request
        :type core_num: int

        :return: None
        """
        for src, dest in zip(self.path, self.path[1:]):
            src_dest = (src, dest)
            dest_src = (dest, src)

            # Remember, Python list indexing is up to and NOT including!
            tmp_set = set(self.net_spec_db[src_dest]['cores_matrix'][core_num][start_slot:end_slot - 1])
            rev_tmp_set = set(self.net_spec_db[dest_src]['cores_matrix'][core_num][start_slot:end_slot - 1])

            if tmp_set != {0.0} or rev_tmp_set != {0.0}:
                raise BufferError("Attempted to allocate a taken spectrum.")

            self.net_spec_db[src_dest]['cores_matrix'][core_num][start_slot:end_slot - 1] = self.req_id
            self.net_spec_db[dest_src]['cores_matrix'][core_num][start_slot:end_slot - 1] = self.req_id

            # A guard band for us is a -1, as it's important to differentiate the rest of the request from it
            if self.guard_slots:
                if self.net_spec_db[src_dest]['cores_matrix'][core_num][end_slot - 1] != 0.0 or \
                        self.net_spec_db[dest_src]['cores_matrix'][core_num][end_slot - 1] != 0.0:
                    raise BufferError("Attempted to allocate a taken spectrum.")

                self.net_spec_db[src_dest]['cores_matrix'][core_num][end_slot - 1] = (self.req_id * -1)
                self.net_spec_db[dest_src]['cores_matrix'][core_num][end_slot - 1] = (self.req_id * -1)

    def allocate_lps(self):
        """
        Attempts to perform light path slicing (LPS) to allocate a request.

        :return: True if LPS is successfully carried out, False otherwise
        """
        if self.chosen_bw == '25' or self.max_slices == 1:
            return False

        path_length = find_path_len(self.path, self.topology)
        modulation_formats = sort_dict_keys(self.mod_per_bw)

        for bandwidth, modulation_dict in modulation_formats:
            if int(bandwidth) >= int(self.chosen_bw):
                continue

            tmp_format = get_path_mod(modulation_dict, path_length)
            if tmp_format is False:
                continue

            num_slices = int(int(self.chosen_bw) / int(bandwidth))
            if num_slices > self.max_slices:
                continue

            self.num_transponders += num_slices - 1

            for _ in range(num_slices):
                slot_range = modulation_dict[tmp_format]['slots_needed']
                spectrum_assignment = SpectrumAssignment(self.path, slot_range, self.net_spec_db,
                                                         guard_slots=self.guard_slots, single_core=self.single_core,
                                                         is_sliced=True, alloc_method=self.alloc_method)
                selected_spectrum = spectrum_assignment.find_free_spectrum()

                if selected_spectrum is False:
                    self.release()
                    return False

                self.allocate(start_slot=selected_spectrum['start_slot'], end_slot=selected_spectrum['end_slot'],
                              core_num=selected_spectrum['core_num'])

            return True

        return False

    def handle_lps(self):
        """
        This method attempts to perform light path slicing (LPS) to allocate a request.
        If successful, it returns a response containing the allocated path, modulation format,
        and the number of transponders used. Otherwise, it returns a tuple of False and the
        value of self.dist_block indicating whether the allocation failed due to congestion or
        a length constraint.

        :return: A tuple containing the response and the updated network database or False and self.dist_block
        """
        if self.allocate_lps():
            resp = {
                'path': self.path,
                'mod_format': None,
                'is_sliced': True,
            }
            return resp, self.net_spec_db, self.num_transponders

        return False, self.dist_block

    def handle_event(self, request_type):
        """
        Handles any event that occurs in the simulation. This is the main method in this class. Returns False if a
        request has been blocked.

        :param request_type: Whether the request is an arrival or shall be released
        :type request_type: str

        :return: The response with relevant information, network database, and physical topology
        """
        # Even if the request is blocked, we still use one transponder
        self.num_transponders = 1
        # Whether the block is due to a distance constraint, else is a congestion constraint
        self.dist_block = False

        if request_type == "release":
            self.release()
            return self.net_spec_db

        routing_obj = Routing(source=self.source, destination=self.destination,
                              topology=self.topology, net_spec_db=self.net_spec_db,
                              mod_formats=self.mod_per_bw[self.chosen_bw], bandwidth=self.chosen_bw)

        if self.sim_type == 'yue':
            selected_path, path_mod = routing_obj.shortest_path()
        elif self.sim_type == 'arash':
            selected_path = routing_obj.least_congested_path()
            path_mod = 'QPSK'
        else:
            raise NotImplementedError

        if selected_path is not False:
            self.path = selected_path
            if path_mod is not False:
                slots_needed = self.mod_per_bw[self.chosen_bw][path_mod]['slots_needed']
                spectrum_assignment = SpectrumAssignment(self.path, slots_needed, self.net_spec_db,
                                                         guard_slots=self.guard_slots, is_sliced=False,
                                                         alloc_method=self.alloc_method)

                selected_sp = spectrum_assignment.find_free_spectrum()

                if selected_sp is not False:
                    resp = {
                        'path': selected_path,
                        'mod_format': path_mod,
                        'is_sliced': False
                    }

                    self.allocate(selected_sp['start_slot'], selected_sp['end_slot'], selected_sp['core_num'])
                    return resp, self.net_spec_db, self.num_transponders

                # Attempt to slice the request due to a congestion constraint
                return self.handle_lps()

            # Attempt to slice the request due to a distance constraint
            return self.handle_lps()

        raise NotImplementedError
