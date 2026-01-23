"""
Merge the WEncoder outputs of multiple sessions (from multiple subjects) into a single CSV file with the characters data of all subjects,
and a single file with the trial data of all subjects.

The combination of all sessions is called a "dataset"; it reflects a single task/condition.
Each dataset is defined by a prefix (e.g., 'wencoder_1') and the number of blocks in it.
"""
import math
import os
import pandas as pd
import glob
import re
import scipy.stats
import inspect
from collections import namedtuple

import writracker.utils as u


ColGeneratorSpec = namedtuple('ColGeneratorSpec', ['generator', 'nparams'])


#-----------------------------------------------------------------------------
class Merger(object):

    def __init__(self, new_cols_trials=None, new_cols_chars=None, traj_file_prefix='trajectory_trial_', has_block_col=True,
                 set_response_in_ok_trials=False, min_ntrials_in_session=0, trace=False):
        """
        :param new_cols_trials: Specification of new columns to create in the trials.csv file.
                The specification is a dict; in each entry,
                Key = the new column name (or tuple/list of several new column names)
                Value = A function to generate the new value/s (called for each row).
                    The function returns, the new columns value (or a list of values if the dict key specifiefs several columns).
                    The function has 3 arguments: the row, the dataset directory, the subject ID
        :param new_cols_chars: Specification of new columns to create in the characters.csv file.
                The specification is a dict; in each entry,
                Key = the new column name (or tuple/list of several new column names)
                Value = A function to generate the new value/s (called for each row).
                    The function returns, the new columns value (or a list of values if the dict key specifiefs several columns).
                    The function's first argument is the row from characters.csv. It can also get two additinal argumetns:
                    the dataset directory + the subject ID. It can also get a 4th argument: the trial (a DataFrame row from trials.csv).
        :param traj_file_prefix:
        :param has_block_col: Whether the output should include a "block" column (if yes, expecting it in the input too)
        :param min_ntrials_in_session: Ignore sessions with fewer trials than this number
        :param set_response_in_ok_trials: If True, set the response to be equal to the target in all trials with rc=='OK'
        """
        self.new_cols_trials = self._parse_generators(new_cols_trials, valid_n_params={1, 3, 4})
        self.new_cols_chars = self._parse_generators(new_cols_chars, valid_n_params={1, 3, 4})
        self.traj_file_prefix = traj_file_prefix
        self.has_block_col = has_block_col
        self.merge_errors = {}
        self.overriden_cols = set()
        self.set_response_in_ok_trials = set_response_in_ok_trials
        self.min_ntrials_in_session = min_ntrials_in_session
        self.trace = trace

    #-------------------------------------------------------------------
    def _parse_generators(self, generators, valid_n_params):
        """ Detect each generator's number of parameters (and validate it) """
        if generators is None:
            return {}

        result = {}
        for key, gen in generators.items():
            try:
                nparams = len(inspect.signature(gen).parameters)
            except TypeError as e:
                print(f'ERROR: cannot parse the generator of column {key}: generator="{gen}": {e}')
                continue

            if nparams not in valid_n_params:
                expected = " or ".join(str(s) for s in valid_n_params)
                print(f'ERROR: generator for column {key} has {nparams} parameters, but expected {expected}')
                continue

            result[key] = ColGeneratorSpec(generator=gen, nparams=nparams)

        return result

    #-------------------------------------------------------------------
    def merge_dataset(self, subj_location, find_session_dirs, out_chars_fn=None, out_trials_fn=None):
        """
        Merge character.csv files of multiple subjects into a single file
        and trials.csv files of multiple subjects into a single file

        :param subj_location: a dictionary of subject IDs and their locations (e.g., a directory)
        :param find_session_dirs: a function that finds the directories of relevant sessions in given subject's directory.
                                  The function should return a list of SessionDir objects
        :param out_chars_fn: the output file name (CSV, one line per character)
        :param out_trials_fn: the output file name (CSV, one line per trial)
        """
        trials_data = []
        chars_data = []
        self.merge_errors = dict(N_MISSING_IN_TRIALS_CSV=0, N_MISSING_TRAJ_FILES=0)

        for subj_id, subj_loc in subj_location.items():
            if self.trace:
                print(f'\nProcessing subject {subj_id} in {subj_loc}')

            ds_dirs = find_session_dirs(subj_loc)
            if ds_dirs is None:
                print(f"ERROR: Subject {subj_id} was not loaded due to errors in {subj_loc}")
                continue

            for ds_dir in ds_dirs:
                curr_trials_df, curr_chars_df = self._load_session(ds_dir, subj_id)
                if curr_trials_df.empty:
                    continue

                self._generate_new_columns(curr_trials_df, curr_chars_df, ds_dir, subj_id)
                trials_data.append(curr_trials_df)
                chars_data.append(curr_chars_df)

        all_trials_df = self._merge_trials(trials_data)
        all_chars_df = self._merge_characters(chars_data)
        all_chars_df = self._add_columns_to_merged_chars_df(all_chars_df, all_trials_df)

        if out_trials_fn is not None:
            all_trials_df = self._add_columns_to_merged_trials_df(all_trials_df, all_chars_df)
            all_trials_df.to_csv(out_trials_fn, index=False, float_format='%.3g')

        if out_chars_fn is not None:
            all_chars_df.to_csv(out_chars_fn, index=False, float_format='%.5g')

        return all_chars_df

    #-------------------------------------------------------------------
    def _load_session(self, ds_dir, subj_id):
        trials_df = self._load_session_trials(f'{ds_dir.dir_name}/trials.csv', ds_dir, subj_id)
        chars_df = self._load_session_characters(ds_dir, trials_df, subj_id)
        return trials_df, chars_df

    #-------------------------------------------------------------------
    def _generate_new_columns(self, trials_df, chars_df, ds_dir, subj_id):

        self._apply_trials_col_generators(trials_df, ds_dir, subj_id, chars_df)
        self._apply_char_col_generators(chars_df, ds_dir, subj_id, trials_df)

        for col in list(chars_df):
            if col != 'extends' and chars_df[col].isna().all():
                print(f'NOTE: column "{col}" is empty in all rows of subject {subj_id} dataset {ds_dir.dir_name}')
                break

    #-------------------------------------------------------------------
    def _merge_trials(self, trials_df_per_subdir):
        return pd.concat(trials_df_per_subdir, axis='rows')

    #-------------------------------------------------------------------
    def _add_columns_to_merged_trials_df(self, trials_df, chars_df):

        trials_df = self._copy_col_from_char1_to_trials(trials_df, chars_df, 'pre_trial_delay')
        trials_df = self._copy_col_from_char1_to_trials(trials_df, chars_df, 'pre_trial_delay_z')
        if 'cross_triplet_delay' in chars_df:
            trials_df = self._copy_col_from_char1_to_trials(trials_df, chars_df, 'cross_triplet_delay')
            trials_df = self._copy_col_from_char1_to_trials(trials_df, chars_df, 'cross_triplet_delay_z')

        return trials_df

    #-------------------------------------------------------------------
    def _copy_col_from_char1_to_trials(self, trials_df, chars_df, col_name):
        char1_df = chars_df[chars_df.char_num == 1][self.merge_key() + [col_name]]
        return trials_df.merge(char1_df, on=self.merge_key(), how='left')

    #-------------------------------------------------------------------
    def _merge_characters(self, chars_df_per_subdir):

        to_concat = [df for df in chars_df_per_subdir if not df.empty]
        merged_df = pd.concat(to_concat, axis='rows')

        for first_col in ('block', 'subject'):
            if first_col not in list(merged_df):
                continue
            merged_df = merged_df[[first_col] + [c for c in list(merged_df) if c != first_col]]

        return merged_df

    #-------------------------------------------------------------------
    def _add_columns_to_merged_chars_df(self, df, trials_df):

        df = self.update_prev_and_next_char(df)

        #-- Add RC from trials
        df = df.merge(trials_df[self.merge_key() + ['rc']], on=self.merge_key(), how='left')

        variant_length = 'target_len' in df and len(df.target_len.unique()) > 1

        #-- The pre-char delay of character #1 is set to be the pre-trial delay
        df = self.update_pre_char_delay_at_trial_level(df, 'pre_trial_delay', per_length=variant_length, char_num=1)
        if 'dec_pos' in df:
            df = self.update_pre_char_delay_at_trial_level(df, 'cross_triplet_delay', per_length=variant_length, dec_pos=3)

        if 'sound_file_length' in df:
            df['post_stim_char1_delay'] = df.pre_trial_delay - df.sound_file_length
            self.zscore_col(df, 'post_stim_char1_delay', True)

        return df

    #-------------------------------------------------------------------
    def _load_session_trials(self, trials_fn, ds_dir, subj_id):
        """
        Add a DataFrame with the current dataset's trials to the trials_data array
        """

        if self.trace:
            print('Loading trials file')

        raw_df = pd.read_csv(trials_fn)
        if raw_df.shape[0] != (raw_df.trial_id.astype(str) + raw_df.sub_trial_num.astype(str)).nunique():
            print(f'ERROR: duplicate trials in {ds_dir.dir_name}/trials.csv ({raw_df.shape[0]} rows but only {raw_df.trial_id.nunique()} unique trial IDs). This dataset was ignored.')
            return pd.DataFrame()

        if self.has_block_col and 'block' not in raw_df:
            print(f'ERROR: block column is missing in {ds_dir.dir_name}/trials.csv but expected. This dataset was ignored.')
            return pd.DataFrame()

        if raw_df.shape[0] < self.min_ntrials_in_session:
            print(f'WARNING: only {raw_df.shape[0]} trials in {ds_dir.dir_name}/trials.csv, fewer than the required minimum of {self.min_ntrials_in_session}. This dataset was ignored.')
            return pd.DataFrame()

        all_rc = raw_df.rc.str.strip()
        new_df = dict(subject=[subj_id] * raw_df.shape[0],
                      trial_id=raw_df.trial_id,
                      target_id=raw_df.target_id,
                      sub_trial_num=raw_df.sub_trial_num,
                      target=raw_df.target,
                      response=[trg if (self.set_response_in_ok_trials and rc == 'OK') else resp
                                for trg, resp, rc in zip(raw_df.target, raw_df.response, all_rc)],
                      time_in_session=raw_df.time_in_session,
                      rc=all_rc,
                      traj_file_name=raw_df.traj_file_name)

        new_df = pd.DataFrame(new_df)

        if 'sound_file_length' in raw_df:
            new_df['sound_file_length'] = raw_df.sound_file_length

        if self.has_block_col:
            assert ds_dir.block_unique is not None, "No block number was specified"
            new_df['block'] = [ds_dir.block_unique] * raw_df.shape[0]

        return new_df

    #-------------------------------------------------------------------
    def _apply_trials_col_generators(self, new_df, ds_dir, subj_id, chars_df):
        """ Add new columns to the trials DataFrame """

        trial_characters = chars_df.groupby(['trial_id', 'sub_trial_num'])

        rows = [dict(row) for _, row in new_df.iterrows()]

        for new_col_name, (new_col_generator, nparams) in self.new_cols_trials.items():
            if self.trace:
                print(f'  Add column {new_col_name} to trials file')

            if nparams == 1:
                def gen_args(row):
                    return row,
            elif nparams == 3:
                def gen_args(row):
                    return row, ds_dir, subj_id
            elif nparams == 4:
                def gen_args(row):
                    trial_key = row['trial_id'], row['sub_trial_num']
                    return row, ds_dir, subj_id, trial_characters.get_group(trial_key) if trial_key in trial_characters.groups else pd.DataFrame()
            else:
                raise ValueError(f'Invalid number of parameters ({nparams}) for column generator {new_col_name}')

            self.apply_generator(new_col_generator, new_col_name, gen_args, rows, new_df)

    #-------------------------------------------------------------------
    def apply_generator(self, new_col_generator, new_col_name, gen_args_func, rows, new_df):

        if len(rows) == 0:
            return

        new_col_values = [new_col_generator(*gen_args_func(row)) for row in rows]

        if isinstance(new_col_name, str) and new_col_name.startswith('__'):
            # No new values generated. This generator probably just keeps stuff on 'row'
            return

        if u.is_collection(new_col_name):
            new_col_names = new_col_name
        else:
            new_col_names = new_col_name,
            new_col_values = [[v] for v in new_col_values]

        for i, col_name in enumerate(new_col_names):

            if col_name not in self.overriden_cols:
                if col_name in new_df:
                    print(f'WARNING: column "{col_name}" generated twice / overriden')
                    self.overriden_cols.add(col_name)
                elif col_name in rows[0]:
                    print(f'WARNING: column "{col_name}" overrides a column that exists in the input data')
                    self.overriden_cols.add(col_name)

            new_df[col_name] = [v[i] for v in new_col_values]
            for row, v in zip(rows, new_col_values):
                row[col_name] = v[i]

    #-------------------------------------------------------------------
    def _load_session_characters(self, ds_dir, trials, subj_id):
        """
        Load characters.csv file of the current session, and add new columns to it.
        """
        if self.trace:
            print('Loading characters file')

        #-- Read characters.csv file -- only trials with rc=OK
        curr_chars_df = pd.read_csv(ds_dir.filename, dtype=dict(char=str))
        curr_chars_df = self.filter_good_trials(curr_chars_df, ds_dir.dir_name)

        curr_chars_df['subject'] = subj_id

        if self.set_response_in_ok_trials:
            ddf_char = curr_chars_df.\
                drop('response', axis='columns').\
                merge(trials[['trial_id', 'sub_trial_num', 'response']], on=['trial_id', 'sub_trial_num'], how='left')
            curr_chars_df.response = ddf_char.response

        return curr_chars_df

    #-------------------------------------------------------------------
    def _apply_char_col_generators(self, curr_chars_df, ds_dir, subj_id, trials):

        get_trial_by_id = GetTrialWithID(trials)

        rows = [dict(row) for _, row in curr_chars_df.iterrows()]

        for new_col_name, (new_col_generator, nparams) in self.new_cols_chars.items():

            if self.trace:
                print(f'  Add column {new_col_name} to characters file')

            if nparams == 1:
                def gen_args(row):
                    return row,
            elif nparams == 3:
                def gen_args(row):
                    return row, ds_dir, subj_id
            elif nparams == 4:
                def gen_args(row):
                    return row, ds_dir, subj_id, get_trial_by_id(row['trial_id'])
            else:
                raise ValueError(f'Invalid number of parameters ({nparams}) for column generator {new_col_name}')

            self.apply_generator(new_col_generator, new_col_name, gen_args, rows, curr_chars_df)

    #-------------------------------------------------------------------
    def update_prev_and_next_char(self, data):
        """ Update, in each row, the previous and next characters """
        merge_key = self.merge_key() + ['char_num']

        next_char_df = data.copy()
        next_char_df['char_num'] = next_char_df.char_num - 1
        next_char_df = next_char_df[merge_key + ['char']]
        next_char_df.rename(columns={'char': 'next_char'}, inplace=True)

        prev_char_df = data.copy()
        prev_char_df['char_num'] = prev_char_df.char_num + 1
        prev_char_df = prev_char_df[merge_key + ['char']]
        prev_char_df.rename(columns={'char': 'prev_char'}, inplace=True)

        data = data.merge(next_char_df, on=merge_key, how='left')
        data = data.merge(prev_char_df, on=merge_key, how='left')

        return data


    #-------------------------------------------------------------------
    def update_pre_char_delay_at_trial_level(self, data, col_name, per_length, char_num=None, dec_pos=None):
        """
        Set the pre-char delay of a particular character over all rows of the corresponding trial
        Z-score over all subjects together, either separately for each target length or not
        :param col_name: the name of the new column
        :param char_num: the number of the character to use (1 = leftmost)
        :param dec_pos: the decimal position of the digit to use (1 = rightmost)
        :param per_length: if True, z-score separately for each target length
        """

        assert (char_num is None) != (dec_pos is None)

        char_data = data[(data.dec_pos == dec_pos) if char_num is None else data.char_num == char_num].reset_index(drop=True)
        char_data[col_name] = char_data.pre_char_delay

        self.zscore_col(char_data, col_name, per_length)

        data = data.merge(char_data[self.merge_key() + [col_name, col_name+'_z']],
                          on=self.merge_key(), how='left')

        return data

    #-------------------------------------------------------------------
    def zscore_col(self, data, col_name, per_length):
        """
        Z-score a given column; potentially per length
        """
        if per_length:
            data[col_name + '_z'] = 0.0
            for target_len in data.target_len.unique():
                data.loc[data.target_len == target_len, col_name + '_z'] = \
                    scipy.stats.zscore(data[col_name][data.target_len == target_len], nan_policy='omit')
        else:
            data[col_name + '_z'] = scipy.stats.zscore(data[col_name], nan_policy='omit')


    #-------------------------------------------------------------------
    def merge_key(self):
        key = ['subject']
        if self.has_block_col:
            key.append('block')
        key.append('trial_id')
        key.append('sub_trial_num')
        return key

    #-------------------------------------------------------------------
    def filter_good_trials(self, df, dir_name):

        trials = pd.read_csv(dir_name + '/trials.csv')
        target_ids = [None if math.isnan(tid) else tid for tid in trials.target_id]
        trials_in_trials_csv = {(trial, subtrial, target) for trial, subtrial, target in zip(trials.trial_id, trials.sub_trial_num, target_ids)}

        trials_with_traj_files, traj_file_names = self.find_traj_files(dir_name)

        self._check_if_trials_are_missing_in_trials_csv(trials_in_trials_csv, trials_with_traj_files, dir_name)

        missing_traj_files = [fn for fn in trials.traj_file_name if fn not in traj_file_names]
        if len(missing_traj_files) > 0:
            print(f'ERROR in {dir_name}: trajectory files are missing for some trials: {missing_traj_files}')
            self.merge_errors['N_MISSING_TRAJ_FILES'] += len(missing_traj_files)

        good_trials = trials.trial_id[trials.rc == 'OK']
        df = df[df.trial_id.isin(good_trials)]

        return df

    #-------------------------------------------------------------------
    def _check_if_trials_are_missing_in_trials_csv(self, trials_in_trials_csv, trials_with_traj_files, dir_name):

        missing_in_trials_csv = [(trial, subtrial, target) for (trial, subtrial), target in trials_with_traj_files.items()
                                 if (trial, subtrial, target) not in trials_in_trials_csv]
        if len(missing_in_trials_csv) > 0:
            print(f'WARNING in {dir_name}: some trials have trajectory files but they are not in trials.csv: ')
            for trial, subtrial, target in missing_in_trials_csv:
                print(f'    Trial #{trial}/{subtrial} (target #{target})')
            self.merge_errors['N_MISSING_IN_TRIALS_CSV'] += len(missing_in_trials_csv)

    #-------------------------------------------------------------------
    def find_traj_files(self, dir_name):
        """
        Find all trajectory files.
        Return a dictionary of trial_id -> trial_id
        """
        result = {}

        traj_files = glob.glob(f'{dir_name}/trajectory_*.csv')
        for filename in traj_files:
            basename = os.path.basename(filename)
            m = re.match(f'^{self.traj_file_prefix}(\\d+)(_(\\d+))?_target_(\\d+).csv$', basename)
            if m is None:
                print(f'Warning: invalid trajectory file name "{basename}" in {dir_name}')
                continue
            trial_id = int(m.group(1))
            subtrial_num = 1 if m.group(3) is None else int(m.group(3))
            result[(trial_id, subtrial_num)] = int(m.group(4))

        return result, [os.path.basename(fn) for fn in traj_files]


#-------------------------------------------------------------------
class GetTrialWithID(object):

    def __init__(self, trials_df):
        self.trials_df = trials_df

    def __call__(self, trial_id):
        return self.trials_df[self.trials_df.trial_id == trial_id].iloc[0]


#-------------------------------------------------------------------
def find_dataset_directories(subj_dir, ds_prefix, filename, nblocks, print_errors=True):
    """
    Find all the directories containing the subject's data for a specific dataset.
    Assuming that each subject has a directory and within it several subdirectories, only some of which relevant to the current
    dataset, and each of these directories contains a file with the given filename.

    :param subj_dir: the subject's base directory
    :param ds_prefix: the prefix of the dataset directories
    :param filename: the name of the file to look for in each directory
    :param nblocks: the number of blocks expected in this dataset
    :param print_errors: if True, print errors to the console
    :return: a list of filenames or directory/file names, or None if there are errors
    """

    assert '(' not in ds_prefix
    assert nblocks <= 9

    if '#' in ds_prefix:
        dirname_pattern = ds_prefix.replace('#', f'[1-{nblocks}]')
    else:
        dirname_pattern = f'{ds_prefix}_?([1-{nblocks}])'

    ds_sub_dirs = []
    for dir_name in os.listdir(subj_dir):
        m = re.match(dirname_pattern, dir_name)
        if m is None:
            continue
        target_fn = f'{subj_dir}/{dir_name}/{filename}'
        if os.path.isfile(target_fn):
            found_block = int(m.group(1))
            ds_sub_dirs.append(EncodedSessionDir(dir_name=f'{subj_dir}/{dir_name}', filename=target_fn, block=found_block))

    found_blocks = {sd.block for sd in ds_sub_dirs}
    if len(found_blocks) < nblocks:
        if print_errors:
            if len(found_blocks) > 0:
                missing = [f'#{i}' for i in range(1, nblocks+1) if i not in found_blocks]
                print('ERROR in {}/{}: Some sessions are missing: {}'.format(os.path.basename(subj_dir), ds_prefix, ', '.join(missing)))
            else:
                print('WARNING in {}/{}: No data found'.format(os.path.basename(subj_dir), ds_prefix))
        return None

    for block in found_blocks:
        curr_block_inds = [i for i, sd in enumerate(ds_sub_dirs) if sd.block == block]
        if len(curr_block_inds) > 1:
            for i, block_ind in enumerate(curr_block_inds):
                ds_sub_dirs[block_ind].subblock = chr(ord('a') + i)

    ds_sub_dirs.sort(key=lambda sd: (sd.block, (sd.subblock or 0)))

    return ds_sub_dirs


#-------------------------------------------------------------------
class EncodedSessionDir(object):
    """
    Describes the directory of one encoded session.
    We assume that the subject had several sessions in a given task/condition: multiple block, and sometimes each block
    could be divided into sub-blocks for technical reasons
    """

    def __init__(self, dir_name, filename, block):
        """
        :param dir_name: Session directory name (full path)
        :param filename: Relevant filename within that sessions - e.g., trials.csv (full path)
        :param block: Block number (assuming the subject had several sessions in a given task/condition)
        """
        self.dir_name = dir_name
        self.filename = filename
        self.block = block
        self.subblock = None

    @property
    def block_unique(self):
        return str(self.block) if self.subblock is None else f'{self.block}{self.subblock}'

    @property
    def dir_basename(self):
        return os.path.basename(self.dir_name)
