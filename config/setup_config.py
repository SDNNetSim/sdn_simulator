import configparser

from helper_scripts.os_helpers import create_dir
from config import config_constants


def _copy_dict_vals(dest_key: str, dictionary: dict):
    """
    Given a dictionary, copy the values from key s1 to a given key.

    :param dest_key: The destination key where the values will be copied to.
    :type dest_key: str

    :param dictionary: The dictionary containing s1 and its values.
    :type dictionary: dict

    :return: An updated dictionary with the values from s1 copied to a custom key in the dictionary.
    :rtype: dict
    """
    dictionary[dest_key] = dict()
    for key, val in dictionary['s1'].items():
        dictionary[dest_key][key] = val

    return dictionary


def _setup_threads(config: configparser.ConfigParser, config_dict: dict, sections: list, option_types: dict,
                   other_options: dict, args_obj: dict):
    """
    Checks if multiple threads should be run. If so, structure each sim's params.

    :param config: The configuration object
    :type config: config.ConfigParser

    :param config_dict: A dictionary containing the main thread with key value pairs.
    :type config_dict: dict

    :param sections: A list of every section in the ini file.
    :type sections: list

    :param option_types: A dictionary of all options along with their desired conversion type.
    :type option_types: dict

    :param other_options: A dictionary of non-required options that may change between sims.
    :type other_options: dict

    :param args_obj: Arguments passed via the command line (if any).
    :type args_obj: dict

    :return: An updated dictionary with parameters for every simulation if they exist.
    :rtype: dict
    """
    for new_thread in sections:
        config_dict = _copy_dict_vals(dest_key=new_thread, dictionary=config_dict)
        # Make desired changes for this thread
        for key, value in config.items(new_thread):
            try:
                target_type = option_types[key]
            except KeyError:
                target_type = other_options[key]
            config_dict[new_thread][key] = target_type(value)
            # TODO: Only support for changing all s<values> as of now
            if args_obj[key] is not None:
                config_dict[new_thread][key] = args_obj[key]

    return config_dict


def read_config(args_obj: dict):
    """
    Reads and structures necessary data from the configuration file in the run_ini directory.

    :param args_obj: Arguments passed via the command line (if any).
    :type args_obj: dict
    """
    config_dict = {'s1': dict()}
    config = configparser.ConfigParser()

    try:
        config.read('config/run_ini/config.ini')

        if not config.has_section('s1') or not config.has_option('s1', 'sim_type'):
            create_dir('config/run_ini')
            raise ValueError("Missing 's1' section in the configuration file or simulation type option. "
                             "Please ensure you have a file called config.ini in the run_ini directory.")

        if config['s1']['sim_type'] == 'arash':
            required_options = config_constants.ARASH_REQUIRED_OPTIONS
        else:
            required_options = config_constants.YUE_REQUIRED_OPTIONS
        other_options = config_constants.OTHER_OPTIONS

        for option in required_options:
            if not config.has_option('s1', option):
                raise ValueError(f"Missing '{option}' in the 's1' section.")

        # Structure config value into a dictionary for the main simulation
        for key, value in config.items('s1'):
            # Convert the values in ini value to desired types since they default as strings
            try:
                target_type = required_options[key]
                config_dict['s1'][key] = target_type(value)
            except KeyError:
                target_type = other_options[key]
                config_dict['s1'][key] = target_type(value)

            # TODO: Only support for changing all s<values> as of now
            if args_obj[key] is not None:
                config_dict['s1'][key] = args_obj[key]

        # Init other options to None if they haven't been specified
        for option in other_options:
            if option not in config_dict['s1']:
                config_dict['s1'][option] = None

        # Ignoring index zero since we've already handled s1, the first simulation
        resp = _setup_threads(config=config, config_dict=config_dict, sections=config.sections()[1:],
                              option_types=required_options, other_options=other_options, args_obj=args_obj)

        # TODO: Revert this to be correct
        policy = resp['s1']['policy']
        # resp['s1'].pop('policy')
        #
        # # New AI arguments structure
        # ai_arguments_base = {
        #     "is_training": "True",
        #     "table_path": "None",
        #     "epsilon": 0.05,
        #     "epsilon_target": 0.01,
        #     "policy": policy,
        #     "learn_rate": 0.01,
        #     "discount": 0.1
        # }
        #
        # # Define the values for alpha, gamma, and epsilon
        # alpha_values = [0.1, 0.01]
        # gamma_values = [0.1, 0.2, 0.9, 0.8]
        # epsilon_values = [0.1, 0.05]
        #
        # config_counter = 1  # Start counter for naming configurations
        #
        # for alpha in alpha_values:
        #     for gamma in gamma_values:
        #         for epsilon in epsilon_values:
        #             # Update the ai_arguments with the new values
        #             ai_arguments = ai_arguments_base.copy()
        #             ai_arguments["learn_rate"] = alpha
        #             ai_arguments["discount"] = gamma
        #             ai_arguments["epsilon"] = epsilon
        #
        #             # Create a new configuration
        #             new_config = resp['s1'].copy()
        #             new_config["ai_arguments"] = ai_arguments
        #
        #             # Add to the dictionary with a unique key
        #             key = f's{config_counter}'
        #             resp[key] = new_config
        #
        #             # Increment the counter for the next key
        #             config_counter += 1

        return resp

    except configparser.Error as error:
        print(f"Error reading configuration file: {error}")
        return None


if __name__ == '__main__':
    read_config(args_obj={'Test': None})
