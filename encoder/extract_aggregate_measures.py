import os
import analyze
from analyze.transform import GetBoundingBox, AggFunc
import encoder
from encoder import dataiooldrecorder

input_dir = r'C:\Users\Ron\Documents\GitHub\new\raw'
output_dir = r'C:\Users\Ron\Documents\GitHub\new\output'


#-------------------------------------------------------
def trial_ok(trial):
    return trial['rc'] == 'OK'

#-------------------------------------------------------
def get_pre_char_delay(trial, character):
    """
    The delay between this character and the previous one
    """
    return round(character.pre_char_delay)

#-------------------------------------------------------
def get_post_char_delay(trial, character):
    """
    The delay between this character and the next one
    """
    return round(character.post_char_delay)

#-------------------------------------------------------
def get_pre_char_distance(trial, character, prev_agg):
    """
    The horizontal distance between this character and the previous one (rely on the previously-calculated bounding box)
    """
    charnum = character.char_num
    if charnum in prev_agg and charnum - 1 in prev_agg:
        char_inf = prev_agg[charnum]
        prev_char_inf = prev_agg[charnum - 1]
        return char_inf['x'] - (prev_char_inf['x'] + prev_char_inf['width'])
    else:
        return None

#-------------------------------------------------------
def get_post_char_distance(trial, character, prev_agg):
    """
    The horizontal distance between this character and the next one (rely on the previously-calculated bounding box)
    """
    charnum = character.char_num
    if charnum in prev_agg and charnum + 1 in prev_agg:
        char_inf = prev_agg[charnum]
        next_char_inf = prev_agg[charnum + 1]
        return next_char_inf['x'] - (char_inf['x'] + char_inf['width'])
    else:
        return None



#-------------------------------------------------------

#-- The list of the aggregations to perform (each becomes one or more columns in the resulting CSV file)
agg_func_specs = (
    AggFunc(GetBoundingBox(1.0, 1.0), ('x', 'width', 'y', 'height')),
    AggFunc(get_pre_char_delay, 'pre_char_delay'),
    AggFunc(get_post_char_delay, 'post_char_delay'),
    AggFunc(get_pre_char_distance, 'pre_char_distance', get_prev_aggregations=True),
    AggFunc(get_post_char_distance, 'post_char_distance', get_prev_aggregations=True),
)

exp = encoder.dataiooldrecorder.load_experiment_trajwriter(input_dir, trial_index_filter=trial_ok)

analyze.transform.aggregate_characters(exp.trials, agg_func_specs=agg_func_specs, subj_id=os.path.basename(input_dir),
                                          trial_filter=lambda trial:trial.rc == 'OK',
                                          out_filename=output_dir + '/ADME_main.csv', save_as_attr=False)
