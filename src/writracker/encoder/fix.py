import numpy as np

from writracker.encoder import dataio, manip


#===================================================================================================
#   Fix known problems in encoding
#===================================================================================================

#-------------------------------------------------------------------------------------
def fix_encoding(session_dir, trial_nums=None):
    """
    Fix known problems in the encoding of a session
    """

    print(f'Fixing encoding for session {session_dir}')
    exp = dataio.load_experiment(session_dir)

    strokes_changed = False
    chars_changed = False

    for trial in exp.trials:
        trial_strokes_changed = False
        traj_changed = False
        if trial_nums is None or trial.trial_id in trial_nums:
            if fix_stroke_numbers(trial):
                trial_strokes_changed = True

            if fix_char_numbers(trial):
                trial_strokes_changed = True
                chars_changed = True

            if fix_on_paper_by_char_num(trial):
                trial_strokes_changed = True

            if merge_space_strokes(trial):
                trial_strokes_changed = True

            if trial_strokes_changed:
                strokes_changed = True

            if fix_time_lt_0(trial):
                traj_changed = True

            if trial_strokes_changed or traj_changed:
                save_trial_traj(trial, session_dir)

    if strokes_changed:
        dataio.save_strokes_file(exp.trials, session_dir)

    if chars_changed:
        dataio.save_characters_file(session_dir)


#-------------------------------------------------------------------------------------
def fix_time_lt_0(trial):

    times = np.array([pt.t for pt in trial.traj_points])
    lt0 = times < 0

    if not np.any(lt0):
        return False

    #-- Ensure there are no unexpected time values. We expect times to start from ~ -3600 (1h difference) and increase slowly
    if np.any(np.logical_and(lt0, times > -3500)):
        print(f'Error: Invalid time values in trial #{trial.trial_id}  - negative time > -3500. Trial left unchanged.')
        return False

    #-- If the first time point is negative, make sure it's close to -3600
    first_time_lt0 = np.where(lt0)[0][0]
    if first_time_lt0 == 0 and times[0] > -3595:
        print(f'Error: Invalid time values in trial #{trial.trial_id} - the first time point is negative but too large ({times[0]:.3f}). Trial left unchanged.')
        return False

    #-- Make sure that after fixing the time, the first negative time point will be close to the previous point
    if first_time_lt0 > 0 and times[first_time_lt0] + 3600 - times[first_time_lt0-1] > 0.15:
        print(f'Error: Invalid time values in trial #{trial.trial_id} - the time at index {first_time_lt0} ({times[first_time_lt0]:.3f}) is negative, ' +
              f' but it is too far from the previous time point ({times[first_time_lt0-1]:.3f}). Trial left unchanged.')
        return False

    #-- All time points after the negative one should be negative
    if np.any(times[first_time_lt0:] >= 0):
        print(f'Error: Invalid time values in trial #{trial.trial_id} - some time points after the first negative one are not negative. Trial left unchanged.')
        return False

    #-- Fix!
    print(f'Fixing t<0 for trial #{trial.trial_id} from index {first_time_lt0}.')
    for i in range(first_time_lt0, len(times)):
        trial.traj_points[i].t += 3600

    return True


#-------------------------------------------------------------------------------------
def save_trial_traj(trial, out_dir):
    """
    Save the trial's trajectory file
    """
    traj_file_name = dataio.create_traj_file_name(out_dir, trial.sub_trial_num, trial, trial.trial_id)
    dataio.save_trajectory(trial.strokes, traj_file_name)


#-------------------------------------------------------------------------------------
def fix_stroke_numbers(trial):

    stroke_nums = [s.stroke_num for s in trial.strokes if len(s.trajectory) > 0]
    if stroke_nums == list(range(1, len(stroke_nums) + 1)):
        return False

    print(f'Fixing stroke numbers for trial #{trial.trial_id}')

    strokes = [s for s in trial.strokes if len(s.trajectory) > 0]

    for i, stroke in enumerate([s for s in trial.strokes if len(s.trajectory) > 0]):
        stroke.stroke_num = i + 1

    trial.strokes = strokes

    return True


#-------------------------------------------------------------------------------------
def fix_char_numbers(trial):

    char_nums = [c.char_num for c in trial.characters]
    if char_nums == list(range(1, len(char_nums) + 1)):
        return False

    print(f'Fixing char_nums numbers for trial #{trial.trial_id}')

    for i, char in enumerate(trial.characters):
        char.char_num = i + 1
        for stroke in char.strokes:
            stroke.char_num = char.char_num

    return True


#-------------------------------------------------------------------------------------
def fix_on_paper_by_char_num(trial):

    fixed = False

    for i, stroke in enumerate(trial.strokes):
        if stroke.char_num == 0 and stroke.on_paper:
            print(f'Trial #{trial.trial_id}, set on_paper=False for space stroke #{stroke.stroke_num}')
            stroke.on_paper = False
            fixed = True

    return fixed


#-------------------------------------------------------------------------------------
def merge_space_strokes(trial):

    to_merge = []
    consecutive_space_strokes = []
    for stroke in trial.strokes:
        if stroke.char_num == 0:
            consecutive_space_strokes.append(stroke)
        else:
            if len(consecutive_space_strokes) > 1:
                to_merge.append(consecutive_space_strokes)
            consecutive_space_strokes = []

    if len(consecutive_space_strokes) > 1:
        to_merge.append(consecutive_space_strokes)

    if len(to_merge) == 0:
        return False

    for consecutive_space_strokes in to_merge:
        print(f'Merging {len(consecutive_space_strokes)} space strokes for trial #{trial.trial_id}: {[s.stroke_num for s in consecutive_space_strokes]}')
        manip.merge_strokes(trial, consecutive_space_strokes)

    return True
