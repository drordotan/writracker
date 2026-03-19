"""
Generate new columns in the trials.csv and characters.csv data frames.
"""
import math

import numpy as np
import pandas as pd
import inspect
import scipy.stats
import enum

import mtl.utils as mu


#============================================================================================================
#    Column-generation infra
#============================================================================================================


class GenerateFor(enum.Enum):
    Trials = 'trials'
    Chars = 'characters'


#-- This specifies the scope of the genration function's arguments and return value
class GenerationScope(enum.Enum):
    SingleRow = 1   # Operate on one row at a time
    DataFrame = 2   # Operate on the full data (either one dataset or the whole data, depending on when the generator is applied)


class Phase(enum.Enum):
    DatasetLoaded = 1       # After each dataset
    AllDatasetsLoaded = 2   # After everything was loaded


#--------------------------------------------------------------------------------------------
class GeneratorSpec(object):

    def __init__(self,
                 generate_for: GenerateFor,
                 col_names,
                 generator: callable,
                 phase: Phase = Phase.DatasetLoaded,
                 scope: GenerationScope = GenerationScope.SingleRow):

        if not isinstance(generate_for, GenerateFor):
            raise ValueError(f'Invalid generate_for = "{generate_for}"')

        if not isinstance(scope, GenerationScope):
            raise ValueError(f'Invalid scope = "{scope}"')

        self.generate_for = generate_for
        self.col_names = col_names
        self.generator = generator
        self.phase = phase

        if hasattr(generator, 'scope'):
            if scope is None:
                scope = generator.scope
            elif scope != generator.scope:
                print('WARNING: GeneratorSpec scope overrides generator scope attribute, the scope might be invalid')

        self.scope = scope or GenerationScope.SingleRow

    @property
    def col_names(self):
        return self._col_names

    @col_names.setter
    def col_names(self, value):
        if isinstance(value, str):
            self._col_names = value,
        elif mu.is_collection(value):
            if sum(not isinstance(c, str) for c in value) > 0:
                raise ValueError(f'Non-string column name in "{value}"')
            self._col_names = tuple(value)
        else:
            raise ValueError(f'Invalid column names: {value}')

    @property
    def generator(self):
        return self._generator

    @generator.setter
    def generator(self, func):
        try:
            self.nparams = len(inspect.signature(func).parameters)
        except TypeError as e:
            print(f'ERROR: cannot parse the generator of columns {self.all_col_names}: generator="{self.generator}": {e}')
        self._generator = func

    @property
    def generates_multiple_values(self):
        return len(self.col_names) > 1

    @property
    def export_any_column(self):
        """ Whether the generator exports any column to the target CSV file """
        return sum(not c.startswith('__') for c in self.col_names) > 0

    @property
    def all_col_names(self):
        return ','.join(self.col_names)


#----------------------------------------------------------------------------------------------------
class ColGeneratorsManager(object):

    def __init__(self, generators_spec, trace=False):
        """
        :param generators_spec: Specification of new columns to create in the trials.csv or characters.csv files.
            The specification is a dict; in each entry,
            Key = the name(s) of the new column(s) to create, and where to create them:
                 A single column name, preceded by 't.'/'t_' or 'c.'/'c_' to indicate whether to create it in trials.csv or characters.csv;
                 Or a tuple/list whose first element is 't'/'trials' or 'c'/'chars', and the remaining element/s are the new column name/s
            Value = A function to generate the new value/s (called for each row).
                The function returns the new columns value (or a list of values if the dict key specifiefs several columns).
                The function has 1, 3, or 4 arguments:
                   1 arg = the current row from the relevant CSV file, as a dict
                   3 args = the row, the dataset directory, and the subject ID
                   4 args = Like the 3-arg function. The 4th argument: when creating a new column in characters.csv,
                            this is the trial row (from trials.csv) corresponding to the character's trial_id;
                            When creating a new column in trials.csv, this is a DataFrame with the current trial's characters
        """
        if not mu.is_collection(generators_spec) or sum(not isinstance(g, GeneratorSpec) for g in generators_spec) > 0:
            raise ValueError('generators_spec must be a collection of GeneratorSpec objects')
        self.generators = generators_spec
        self.override_warning_issued = set()
        self.trace = trace

    #-------------------------------------------------------------------
    def generate_custom_columns(self, trials_df, chars_df, phase, subj_id=None, ds_dir=None):
        """
        Generate new columns according to the definitions provided.
        :param phase: The phase in which the generation is executed
        :param ds_dir: The current dataset.
        """

        trials_rows = [dict(row) for _, row in trials_df.iterrows()]
        chars_rows = [dict(row) for _, row in chars_df.iterrows()]

        orig_trials_cols = trials_df.columns
        orig_chars_cols = chars_df.columns

        for generator in self.generators:

            if self.trace:
                print(f'  Add column/s {generator.all_col_names} to {generator.generate_for.value} file')

            if generator.generate_for == GenerateFor.Trials:
                #-- Generate a new column in trials_df
                gen_args = TrialColGenratorArgs(new_col_name=generator.col_names, nparams=generator.nparams,
                                                ds_dir=ds_dir, subj_id=subj_id, chars_df=chars_df)
                self.apply_generator(generator, gen_args, trials_rows, trials_df, orig_trials_cols, phase)

            else:
                #-- Generate a new column in chars_df
                gen_args = CharColGenratorArgs(new_col_name=generator.col_names, nparams=generator.nparams,
                                               ds_dir=ds_dir, subj_id=subj_id, trials_df=trials_df)
                self.apply_generator(generator, gen_args, chars_rows, chars_df, orig_chars_cols, phase)

        if trials_df.shape[0] > 0:
            for col in list(trials_df):
                if col != 'extends' and trials_df[col].isna().all():
                    print(f'NOTE: column "{col}" is empty in all trials.csv rows of subject {subj_id} dataset {ds_dir.dir_name}')
                    break

        if chars_df.shape[0] > 0:
            for col in list(chars_df):
                if col != 'extends' and chars_df[col].isna().all():
                    if phase == Phase.AllDatasetsLoaded:
                        print(f'NOTE: column "{col}" is empty in all characters.csv rows')
                    else:
                        print(f'NOTE: column "{col}" is empty in all characters.csv rows of subject {subj_id} dataset {ds_dir.dir_name}')
                    break

    #-------------------------------------------------------------------
    def apply_generator(self, generator, gen_args_func, rows, df, df_col_names_before_generation, phase):
        """
        Apply a column generator to all rows, then add the generated values as new column/s to the DataFrame

        :param phase: Run only if this matches self's phase
        """

        if phase != generator.phase:
            return

        if generator.scope == GenerationScope.SingleRow:
            new_col_values = [generator.generator(*gen_args_func(row)) for row in rows]
        elif generator.scope == GenerationScope.DataFrame:
            new_col_values = generator.generator(df, gen_args_func.ds_dir, gen_args_func.subj_id)
        else:
            raise ValueError(f'Invalid generator scope: {generator.scope}')

        #-- Ensure the generated values are arrays
        if not generator.generates_multiple_values:
            new_col_values = [[v] for v in new_col_values]

        #-- Export the generated values into the data frame
        for i, col_name in enumerate(generator.col_names):

            for row, v in zip(rows, new_col_values):
                row[col_name] = v[i]

            if col_name.startswith('__'):
                continue

            if col_name in df and col_name not in self.override_warning_issued:
                if col_name in df_col_names_before_generation:
                    print(f'WARNING: column "{col_name}" existed in the input data and its value was modified')
                else:
                    print(f'WARNING: column "{col_name}" was generated and then its value was overriden')
                self.override_warning_issued.add(col_name)


            df[col_name] = [v[i] for v in new_col_values]


#--------------------------------------------------------------------------------------------
class CharColGenratorArgs(object):
    """
    Generate arguments for the col-generation function for characters.csv
    """

    def __init__(self, new_col_name, nparams, ds_dir, subj_id, trials_df):
        self.ds_dir = ds_dir
        self.subj_id = subj_id

        if nparams == 1:
            self.generate_args = self.gen_1args

        elif nparams == 3:
            self.generate_args = self.gen_3args

        elif nparams == 4:
            self.trials_df = trials_df
            self.generate_args = self.gen_4args

        else:
            raise ValueError(f'Invalid number of parameters ({nparams}) for column generator {new_col_name}')

    def gen_1args(self, row):
        return row,

    def gen_3args(self, row):
        return row, self.ds_dir, self.subj_id

    def gen_4args(self, row):
        trial = self.trials_df[self.trials_df.trial_id == row['trial_id']].iloc[0]
        return row, self.ds_dir, self.subj_id, trial

    def __call__(self, row):
        return self.generate_args(row)


#--------------------------------------------------------------------------------------------
class TrialColGenratorArgs(object):
    """
    Generate arguments for the col-generation function for trials.csv
    """

    def __init__(self, new_col_name, nparams, ds_dir, subj_id, chars_df):
        self.ds_dir = ds_dir
        self.subj_id = subj_id
        self.chars_df_cols = list(chars_df)

        if nparams == 1:
            self.generate_args = self.gen_1args

        elif nparams == 3:
            self.generate_args = self.gen_3args

        elif nparams == 4:
            self.trial_characters = chars_df.groupby(['trial_id', 'sub_trial_num'])
            self.generate_args = self.gen_4args

        else:
            raise ValueError(f'Invalid number of parameters ({nparams}) for column generator {new_col_name}')

    def gen_1args(self, row):
        return row,

    def gen_3args(self, row):
        return row, self.ds_dir, self.subj_id

    def gen_4args(self, row):
        trial_key = row['trial_id'], row['sub_trial_num']
        if trial_key in self.trial_characters.groups:
            chars_of_curr_trial = self.trial_characters.get_group(trial_key)
        else:
            chars_of_curr_trial = pd.DataFrame({c: [] for c in self.chars_df_cols})

        return row, self.ds_dir, self.subj_id, chars_of_curr_trial

    def __call__(self, row):
        return self.generate_args(row)


#============================================================================================================
#    Generators for specific columns
#============================================================================================================

#----------------------------------------------------------------------------------
class CopyColumnsFromTrialsToChars(object):

    def __init__(self, *col_names):
        self.col_names = col_names

    def __call__(self, rows, _, __, trial):
        result = [trial[col_name] for col_name in self.col_names]
        return result[0] if len(self.col_names) == 1 else result


#----------------------------------------------------------------------------------
class EliminateSpaces(object):
    """ Remove spaces from a field; optionally convert to lower case """

    def __init__(self, col_name, to_lower=False, nan_to_empty_string=True):
        self.col_name = col_name
        self.to_lower = to_lower
        self.nan_to_empty_string = nan_to_empty_string

    def __call__(self, row):
        value = row[self.col_name]
        if self.nan_to_empty_string and isinstance(value, float) and math.isnan(value):
            return ''

        v = value.replace(' ', '')
        if self.to_lower:
            v = v.lower()
        return v


#----------------------------------------------------------------------------------
class ColMapper(object):

    def __init__(self, col_name, mapping):
        self.col_name = col_name
        self.mapping = mapping

    def __call__(self, row):
        value = row[self.col_name]
        return self.mapping.get(value, value)


#----------------------------------------------------------------------------------
def integer_target_length(row):
    """ The number of digits in an integer target """
    return len(str(int(row['target'])))


#-------------------------------------------------------------------
class ZScoreColumn(object):
    """
    Z-score a given column; potentially separately per length
    """

    def __init__(self, col_name, grouping_fld=None, filter_func=None):
        """
        :param col_name: The column containing the values to z-score
        :param grouping_fld: If specified, compute z score separately for each group of rows
        :param filter_func: If specified, Compute z score only for some rows. filter_func is a function that gets a data frame and returns
                            a list for selecting rows (bool of same size; or list of indices to select)
        """
        self.col_name = col_name
        self.grouping_fld = grouping_fld   # z-score separately for each value of this field
        self.filter_func = filter_func     # z-score only these rows. The others remain None.

    #------------------------------------
    def __call__(self, df, _, __):

        if self.filter_func is None:
            result = compute_z_scores(df, self.col_name, self.grouping_fld)
        else:
            result = pd.Series([None] * df.shape[0])
            included_rows = list(self.filter_func(df))
            zscores = compute_z_scores(df[included_rows], self.col_name, self.grouping_fld)
            result[included_rows] = list(zscores)

        return result

    @property
    def scope(self):
        return GenerationScope.DataFrame


#-------------------------------------------------------------------
def compute_z_scores(df, col_name, grouping_fld=None):
    """
    Z-score a given column; potentially separately per length
    """
    if grouping_fld is None:
        return pd.Series(_zscore(df[col_name]))

    #-- Compute per group
    result = np.array([None] * df.shape[0])
    for group in df[grouping_fld].unique():
        result[df[grouping_fld] == group] = _zscore(df[col_name][df[grouping_fld] == group])

    return result


def _zscore(values):
    if sum(~values.isnull()) == 0:
        return [float('nan')] * len(values)
    else:
        return scipy.stats.zscore(values, nan_policy='omit')
