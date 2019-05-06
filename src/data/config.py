import pytz
import yaml


# Configuration object
class Configuration(object):
    """A configuration object deals with everything that we specify
     in the city-specific config file, along with a few hard-coded features
    """
    def __init__(self, filename):
        with open(filename) as f:
            config = yaml.safe_load(f)
        self.default_features, self.categorical_features, \
            self.continuous_features = self.get_feature_list(config)

        self.city = config['city']

        self.startdate = str(config['startdate']) \
            if config['startdate'] else None
        self.enddate = str(config['enddate']) \
            if config['enddate'] else None
        self.timezone = pytz.timezone(config['timezone'])
        self.crashes_files = config['crashes_files']

            
    def get_feature_list(self, config):
        """
        Make the list of features, and write it to the city's data folder
        That way, we can avoid hardcoding the feature list in multiple places.
        If you add extra features, the only place you should need to add them
        is here
        Args:
            Config - the city's config file
        """

        # Features drawn from open street maps
        feat_types = {'f_cat': [], 'f_cont': [], 'default': []}

        # Run through the possible feature types
        for feat_type in ['openstreetmap_features',
                          'waze_features', 'additional_map_features']:
            if feat_type in config:
                if 'categorical' in config[feat_type]:
                    feat_types['f_cat'] += [x for x in config[
                        feat_type]['categorical'].keys()]
                if 'continuous' in config[feat_type]:
                    feat_types['f_cont'] += [x for x in config[
                        feat_type]['continuous'].keys()]

        # Add point-based features, in a different format because
        # each feature has its own file and accompanying details
        if 'data_source' in config and config['data_source']:
            for additional in config['data_source']:
                if 'feat_type' not in additional:
                    feat_types['default'].append(additional['name'])
                elif additional['feat_type'] == 'categorical':
                    feat_types['f_cat'].append(additional['name'])
                elif additional['feat_type'] == 'continuous':
                    feat_types['f_cont'].append(additional['name'])

        # May eventually want to rename this feature to be more general
        # For now, all atr features are continuous
        if 'atr_cols' in config and config['atr_cols']:
            feat_types['f_cont'] += config['atr_cols']

        return feat_types['f_cat'], feat_types['f_cont'], feat_types['default']

