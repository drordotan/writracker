
from writracker.encoder import dataio, manip


#===================================================================================================
#   Fix known problems in encoding
#===================================================================================================

#-------------------------------------------------------------------------------------
def fix_encoding(session_dir):
    """
    Fix known problems in the encoding of a session
    """

    print(f'Fixing encoding for session {session_dir}')
    exp = dataio.load_experiment(session_dir)

    strokes_changed = False
    chars_changed = False

    for trial in exp.trials:
        fix_stroke_numbers(trial)

        if fix_char_numbers(trial):
            strokes_changed = True
            chars_changed = True

        if fix_on_paper_by_char_num(trial):
            strokes_changed = True

        if merge_space_strokes(trial):
            strokes_changed = True
            save_trial_traj(trial, session_dir)

    if strokes_changed:
        dataio.save_strokes_file(exp.trials, session_dir)

    if chars_changed:
        dataio.save_characters_file(session_dir)


#-------------------------------------------------------------------------------------
def save_trial_traj(trial, out_dir):
    """
    Save the trial's trajectory file
    """
    traj_file_name = dataio.create_traj_file_name(out_dir, trial.sub_trial_num, trial, trial.trial_id)
    dataio.save_trajectory(trial.strokes, traj_file_name)


#-------------------------------------------------------------------------------------
def fix_stroke_numbers(trial):

    stroke_nums = [s.stroke_num for s in trial.strokes]
    if stroke_nums == list(range(1, len(stroke_nums) + 1)):
        return False

    print(f'Fixing stroke numbers for trial #{trial.trial_id}')

    for i, stroke in enumerate(trial.strokes):
        stroke.stroke_num = i + 1

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
