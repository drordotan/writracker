"""
Generate new columns in the trials.csv and characters.csv data frames.
"""
import math
import pandas as pd
import inspect
import scipy.stats
import enum

import mtl.utils as mu


#============================================================================================================
#    Column-generation infra
#============================================================================================================

class GenerationScope(enum.Enum):
    SingleRow = 1
    DataFrame = 2


#--------------------------------------------------------------------------------------------
class GeneratorSpec(object):

    def __init__(self, level: str, col_names, generator: callable, scope: GenerationScope = None):
        if level not in ('t', 'c', 'trials', 'chars'):
            raise ValueError(f'Invalid level in ColGeneratorSpec: {level}')

        self.for_trials = 't' in level
        self.col_names = col_names
        self.generator = generator

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
    def target(self):
        return 'trials' if self.for_trials else 'characters'

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
        self.overriden_cols = set()
        self.trace = trace

    #-------------------------------------------------------------------
    def generate_columns(self, trials_df, chars_df, ds_dir, subj_id):

        trials_rows = [dict(row) for _, row in trials_df.iterrows()]
        chars_rows = [dict(row) for _, row in chars_df.iterrows()]

        for generator in self.generators:

            if self.trace:
                print(f'  Add column/s {generator.all_col_names} to {generator.target} file')

            if generator.for_trials:
                #-- Generate a new column in trials_df
                gen_args = TrialColGenratorArgs(new_col_name=generator.col_names, nparams=generator.nparams,
                                                ds_dir=ds_dir, subj_id=subj_id, chars_df=chars_df)
                self.apply_generator(generator, gen_args, trials_rows, trials_df)

            else:
                #-- Generate a new column in chars_df
                gen_args = CharColGenratorArgs(new_col_name=generator.col_names, nparams=generator.nparams,
                                               ds_dir=ds_dir, subj_id=subj_id, trials_df=trials_df)
                self.apply_generator(generator, gen_args, chars_rows, chars_df)

        for col in list(chars_df):
            if col != 'extends' and chars_df[col].isna().all():
                print(f'NOTE: column "{col}" is empty in all rows of subject {subj_id} dataset {ds_dir.dir_name}')
                break

    #-------------------------------------------------------------------
    def apply_generator(self, generator, gen_args_func, rows, df):
        """
        Apply a column generator to all rows, then add the generated values as new column/s to the DataFrame
        """

        #-- Some generators don't export any column to the data frame, but just keep values on 'row'
        if not generator.export_any_column:
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

            if col_name.startswith('__'):
                continue

            if col_name not in self.overriden_cols:
                if col_name in df:
                    print(f'WARNING: column "{col_name}" generated twice / overriden')
                    self.overriden_cols.add(col_name)
                elif len(rows) > 0 and col_name in rows[0]:
                    print(f'WARNING: column "{col_name}" overrides a column that exists in the input data')
                    self.overriden_cols.add(col_name)

            df[col_name] = [v[i] for v in new_col_values]
            for row, v in zip(rows, new_col_values):
                row[col_name] = v[i]


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
        return [trial[col_name] for col_name in self.col_names]


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

    def __init__(self, col_name, per_target_length=False):
        self.col_name = col_name
        self.per_target_length = per_target_length

    def __call__(self, df, _, __):
        return compute_z_scores(df, self.col_name, self.per_target_length)

    @property
    def scope(self):
        return GenerationScope.DataFrame


#-------------------------------------------------------------------
def compute_z_scores(df, col_name, per_target_length):
    """
    Z-score a given column; potentially separately per length
    """
    if not per_target_length:
        return pd.Series(_zscore(df[col_name]))

    #-- Compute per target length
    result = pd.Series([0.0] * df.shape[0])
    for target_len in df.target_len.unique():
        result.loc[df.target_len == target_len] = _zscore(df[col_name][df.target_len == target_len])
    return result


def _zscore(values):
    if sum(~values.isnull()) == 0:
        return [float('nan')] * len(values)
    else:
        return scipy.stats.zscore(values, nan_policy='omit')
