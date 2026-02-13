from _operator import attrgetter


#-------------------------------------------------------------------------------------
class CodedDataset(object):
    """
    All trials of one experiment session
    """

    def __init__(self, trials=(), subj_id=None):
        self._trials = list(trials)
        self.subj_id = subj_id

    @property
    def trials(self):
        return tuple(self._trials)

    @property
    def sorted_trials(self):
        return tuple(sorted(self._trials, key=lambda trial: (trial.block, trial.trial_id)))

    def append(self, trial):
        self._trials.append(trial)

    def sort_trials(self):
        self._trials.sort(key=attrgetter('trial_id'))

    @property
    def n_traj_points(self):
        return sum([trial.n_traj_points for trial in self._trials])


#-------------------------------------------------------------------------------------
class CodedTrial(object):
    """
    Information about one trial in the experiment, after coding.

    The trial contains a series of characters
    """

    def __init__(self, block, trial_id, sub_trial_num, target_id, stimulus, time_in_session, rc, response,
                 sound_file_length, traj_file_name, time_in_day, date, characters, strokes):

        self.block = block
        self.trial_id = trial_id
        self.sub_trial_num = sub_trial_num
        self.target_id = target_id
        self.stimulus = stimulus
        self.time_in_session = time_in_session
        self.rc = rc
        self.source = None
        self.response = response
        self.sound_file_length = sound_file_length
        self.traj_file_name = traj_file_name
        self.time_in_day = time_in_day
        self.date = date
        self.characters = characters
        self.strokes = strokes

    @property
    def traj_points(self):
        return [pt for s in self.strokes for pt in s]

    @property
    def on_paper_points(self):
        """ All points (from any stroke) with z > 0 """
        return [pt for pt in self.traj_points if pt.z > 0]

    @property
    def on_paper_char_points(self):
        """ All points (from any stroke) with z > 0 that belong to a character """
        return [pt for s in self.strokes if s.char_num > 0 for pt in s if pt.z > 0]

    def mirror_in_place(self, x=False, y=False):
        if not (x or y):
            return

        if x:
            for pt in self.traj_points:
                pt.x = -pt.x

        if y:
            for pt in self.traj_points:
                pt.y = -pt.y


#-------------------------------------------------------------------------------------
class Character(object):
    """
    A character, including the above-paper movement before/after it
    """

    def __init__(self, char_num, strokes=(), pre_char_space=None, post_char_space=None, character=None, extends=None):
        """
        :param strokes: a list of the strokes (on/above paper) comprising the character
        :param pre_char_space: The above-paper stroke before the character
        :param post_char_space: The above-paper stroke after the character
        """
        self.char_num = char_num
        self.strokes = list(strokes)
        self.pre_char_space = pre_char_space
        self.post_char_space = post_char_space
        self.character = character
        self.extends = extends


    @property
    def t0(self):
        """
        The time (relative to start-of-trial) when this character started
        """
        return self.strokes[0].trajectory[0].t

    @property
    def duration(self):
        """
        The duration it took to write the character (excluding the pre/post-character delay)
        """
        t_0 = self.strokes[0].trajectory[0].t
        t_n = self.strokes[-1].trajectory[-1].t
        return t_n - t_0

    @property
    def pre_char_delay(self):
        return 0 if self.pre_char_space is None else self.pre_char_space.duration


    @property
    def post_char_delay(self):
        return 0 if self.post_char_space is None else self.post_char_space.duration


#-------------------------------------------------------------------------------------
class Stroke(object):
    """
    A consecutive trajectory part in which the pen is touching the paper, or the movement (above paper) between two such
    adjacent strokes.
    """

    def __init__(self, char_num, stroke_num, on_paper):
        self.stroke_num = stroke_num
        self.char_num = char_num
        self.on_paper = on_paper
        self.trajectory = []


    @property
    def n_traj_points(self):
        return len(self.trajectory)


    @property
    def duration(self):
        """
        The duration (in ms) it took to complete this stroke
        """
        if len(self.trajectory) == 0:
            return 0

        t_0 = float(self.trajectory[0].t)
        t_n = float(self.trajectory[-1].t)
        return t_n - t_0


    def __iter__(self):
        return self.trajectory.__iter__()
