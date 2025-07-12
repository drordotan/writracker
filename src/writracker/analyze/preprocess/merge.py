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


#-----------------------------------------------------------------------------
class Merger(object):

    def __init__(self, new_cols=None, traj_file_prefix='trajectory_trial_', has_block_col=True):
        """

        :param new_cols: A dictionary with new columns to create. The key is the new column name, the value is a function with
                4 parameters: the row, the dataset directory, the subject ID, and the trial (from the trials.csv file).
                If the function does not require the trial, then to save time, replace the function with a 2-elements tuple: (False, function)
        :param traj_file_prefix:
        :param has_block_col:
        """
        self.new_cols = new_cols or {}
        self.traj_file_prefix = traj_file_prefix
        self.has_block_col = has_block_col
        self.merge_errors = {}

    #-------------------------------------------------------------------
    def merge_dataset(self, subj_dirs, find_session_dirs, out_chars_fn=None, out_trials_fn=None):
        """
        Merge character.csv files of multiple subjects into a single file
        and trials.csv files of multiple subjects into a single file

        :param subj_dirs: a dictionary of subject IDs and their directories
        :param find_session_dirs: a function that finds the directories of relevant sessions in given subject's directory.
                                  The function should return a list of SessionDir objects
        :param out_chars_fn: the output file name (CSV, one line per character)
        :param out_trials_fn: the output file name (CSV, one line per trial)
        """
        trials_data = []
        chars_data = []
        self.merge_errors = dict(N_MISSING_IN_TRIALS_CSV=0, N_MISSING_TRAJ_FILES=0)

        for subj_id, subj_dir in subj_dirs.items():
            ds_dirs = find_session_dirs(subj_dir)
            if ds_dirs is None:
                print(f"ERROR: No data found in {subj_dir}")
                continue

            for ds_dir in ds_dirs:
                curr_trials_df = pd.read_csv(ds_dir.dir_name + os.sep + 'trials.csv')
                if out_trials_fn is not None:
                    self._collect_trial_data(curr_trials_df, trials_data, ds_dir, subj_id)

                curr_chars_df = self._load_session_characters(ds_dir, curr_trials_df, subj_id)
                if not curr_chars_df.empty:
                    chars_data.append(curr_chars_df)

        all_chars_df = pd.concat(chars_data, axis='rows')

        for first_col in ('block', 'subject'):
            if first_col not in list(all_chars_df):
                continue
            all_chars_df = all_chars_df[[first_col] + [c for c in list(all_chars_df) if c != first_col]]

        all_chars_df = self.update_prev_and_next_char(all_chars_df)

        all_chars_df = self.update_pre_char_delay_at_trial_level(all_chars_df, 'pre_trial_delay', per_length=True, char_num=1)
        all_chars_df = self.update_pre_char_delay_at_trial_level(all_chars_df, 'cross_triplet_delay', per_length=True, dec_pos=3)

        if 'sound_file_length' in all_chars_df:
            all_chars_df['post_stim_char1_delay'] = all_chars_df.pre_trial_delay - all_chars_df.sound_file_length
            self.zscore_col(all_chars_df, 'post_stim_char1_delay', True)

        if out_trials_fn is not None:
            all_trials_df = pd.concat(trials_data, axis='rows')
            all_trials_df.to_csv(out_trials_fn, index=False, float_format='%.3g')

        if out_chars_fn is not None:
            all_chars_df.to_csv(out_chars_fn, index=False, float_format='%.5g')

        return all_chars_df

    #-------------------------------------------------------------------
    def _collect_trial_data(self, raw_df, trials_data, ds_dir, subj_id):

        new_df = dict(subject=[subj_id] * raw_df.shape[0],
                   trial_id=raw_df.trial_id,
                   target_id=raw_df.target_id,
                   sub_trial_num=raw_df.sub_trial_num,
                   target=raw_df.target,
                   response=raw_df.response,
                   time_in_session=raw_df.time_in_session,
                   rc=raw_df.rc,
                   traj_file_name=raw_df.traj_file_name)

        if 'sound_file_length' in raw_df:
            new_df['sound_file_length'] = raw_df.sound_file_length

        if self.has_block_col:
            new_df['block'] = [ds_dir.block_unique] * raw_df.shape[0]

        trials_data.append(pd.DataFrame(new_df))

    #-------------------------------------------------------------------
    def _load_session_characters(self, ds_dir, trials, subj_id):

        get_trial_by_id = GetTrialWithID(trials)

        curr_chars_df = pd.read_csv(ds_dir.filename, dtype=dict(char=str))
        curr_chars_df = self.filter_good_trials(curr_chars_df, ds_dir.dir_name)

        for new_col_name, new_col_generator in self.new_cols.items():
            if isinstance(new_col_generator, tuple):
                col_generators_need_trial, new_col_generator = new_col_generator
            else:
                col_generators_need_trial = False
            curr_chars_df[new_col_name] = [new_col_generator(row, ds_dir, subj_id,
                                                             get_trial_by_id(row['trial_id']) if col_generators_need_trial else None)
                                           for _, row in curr_chars_df.iterrows()]

        return curr_chars_df

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
    def update_pre_char_delay_at_trial_level(self, data, col_name, char_num=None, dec_pos=None, per_length=True):
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
                print(f'ERROR: invalid trajectory file name "{basename}" in {dir_name}')
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
        :param dir_name: Session directory name
        :param filename: Relevant filename within that sessions
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
