"""
Plot an experiment to a pdf file
"""

import math
import os.path
import re
from matplotlib.backends import backend_pdf
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import patches

import writracker.utils as u
from writracker.encoder.charvalues import get_bounding_box
import writracker.encoder.dataio as dio


#------------------------------------------------------------------------------
class PdfPlotterConfig(object):

    def __init__(self, bounding_box=False, char_order=False, temporal_gaps=False, fraction_of_x_points=None, fraction_of_y_points=None,
                 cols_per_page=2, rows_per_page=5, n_colors=10, trial_title=None, description=None):
        """
        :param trials: either a list of CodedTrial objects or an Experiment object (coded)
        :param out_fn: PDF file name
        :param max_trials: Plot only the first trials in the experiment
        :param bounding_box: plot bounding box for each character (True/False)
        :param char_order: Write the order of writing each character (possible only if bounding_box = True)
        :param temporal_gaps: Plot temporal gaps between adjacent characters (True/False)
        :param fraction_of_x_points: This % of x-points determines the bounding box
        :param fraction_of_y_points: This % of y-points determines the bounding box
        :param cols_per_page: Number of stimuli per row in each page
        :param rows_per_page: Number of stimuli per column in each page
        :param n_colors: Number of grayscale color gradients for showing pen pressure
        :param trial_title: Function that sets each trial's title
        """
        if char_order:
            assert bounding_box, 'Cannot show character order without bounding box'

        self.bounding_box = bounding_box
        self.char_order = char_order
        self.temporal_gaps = temporal_gaps
        self.fraction_of_x_points = fraction_of_x_points
        self.fraction_of_y_points = fraction_of_y_points
        self.cols_per_page = cols_per_page
        self.rows_per_page = rows_per_page
        self.n_colors = n_colors
        self.get_trial_title = trial_title or TrialTitle()
        self.description = None if description is None or str(description).strip() == '' else description

        self.bounding_box_line_width = 0.5


#------------------------------------------------------------------------------
class MultiFilePdfPlotter(object):
    """
    Plot multiple experiments to pdf files, one file per experiment.
    """

    def __init__(self, input_dirs, out_path, config=None):
        """
        :param config: PdfPlotterConfig object
        """
        self.input_dirs = input_dirs
        self.out_path = out_path
        self.config = config or PdfPlotterConfig()
        self.keep_working = True
        self.current_file_plotter = None

    def plot(self):
        for i, ds_dir_name in enumerate(self.input_dirs):

            if not self.keep_working:
                break

            self.on_ds_started(i, ds_dir_name)

            exp = dio.load_experiment(ds_dir_name)
            out_fn = os.path.basename(ds_dir_name)
            try:
                self.current_file_plotter = self.create_one_file_plotter(ds_dir_name,
                                                                         out_fn=f'{self.out_path}/{out_fn}.pdf',
                                                                         config=self.config)
                self.current_file_plotter.init()
                self.current_file_plotter.plot()
            except Exception as e:
                self.on_exception(i, ds_dir_name, e)
                continue

            self.on_ds_finished(i, ds_dir_name)


    def create_one_file_plotter(self, ds_dir_name, out_fn, config):
        return OneFilePdfPlotter(ds_dir_name, out_fn=out_fn, config=config)

    def on_ds_started(self, ds_num, ds_dir):
        pass

    def on_ds_finished(self, ds_num, ds_dir):
        pass

    def on_exception(self, ds_num, ds_dir, e):
        pass

    def stop(self):
        self.keep_working = False
        if self.current_file_plotter is not None:
            self.current_file_plotter.keep_working = False

#------------------------------------------------------------------------------
# noinspection PyMethodMayBeStatic
class OneFilePdfPlotter(object):
    """
    Plot one experiment to pdf
    """

    def __init__(self, input, out_fn, max_trials=None, config=None):
        """
        :param input: a list of CodedTrial objects, an Experiment object (coded), or a directory name (string)
        :param out_fn: PDF file name
        :param max_trials: Plot only the first trials in the experiment
        """
        self.config = config or PdfPlotterConfig()
        self.out_fn = out_fn
        self.max_trials = max_trials
        self.keep_working = True
        self.input = input

    #------------------------------------------------------------------------------
    # noinspection PyAttributeOutsideInit
    def init(self):

        if hasattr(self.input, 'sorted_trials'):
            self.trials = list(self.input.sorted_trials)
        elif isinstance(self.input, str):
            self.trials = dio.load_experiment(self.input).sorted_trials
        elif isinstance(self.input, list):
            self.trials = self.input
        else:
            raise ValueError('Input must be a list of CodedTrial objects, an Experiment object (coded), or a directory name (string)')

        if len(self.trials) == 0:
            raise ValueError('No trials to plot')

        if self.max_trials is not None:
            trials = self.trials[:min(self.max_trials, len(self.trials))]

    #------------------------------------------------------------------------------
    def plot(self):
        """
        Plot the experiment raw data - the characters, as the subject wrote them - and save to a PDF file.

        :param trials: either a list of CodedTrial objects or an Experiment object (coded)
        :param out_fn: PDF file name
        :param cols_per_page: No. of trial columns in each page
        :param rows_per_page: No. of trial rows in each page
        :param n_colors: No. of colors to use to denote level of pressure
        :param max_trials: Plot only the first trials in the experiment
        """

        if not hasattr(self, 'trials'):
            raise Exception('plotter error: init() must be called before plot()')

        trials = list(self.trials)

        n_trials_per_page = self.config.cols_per_page * self.config.rows_per_page

        z_values = np.array([point.z for t in trials for point in t.on_paper_points])
        if len(z_values) == 0:
            print('WARNING: No data to plot' + ('' if self.config.description is None else f' for {self.config.description}'))
            return

        max_z = max(z_values)

        def get_z_levels(z):
            return _convert_z_to_level(z, max_z, self.config.n_colors)

        n_pages = math.ceil(len(trials) / n_trials_per_page)

        self.init_progress_bar()
        n_done = 0

        pdf = backend_pdf.PdfPages(self.out_fn)

        while len(trials) > 0:

            curr_page_n_trials = min(n_trials_per_page, len(trials))
            fig, axes = plt.subplots(self.config.rows_per_page, self.config.cols_per_page)
            fig.subplots_adjust(hspace=.8, wspace=0.3)

            axes = np.reshape(axes, [n_trials_per_page])

            for i in range(curr_page_n_trials):
                trial = trials.pop(0)
                trial.correct_writing_order = None
                n_done += 1
                ax = axes[i]
                ax.get_yaxis().set_visible(False)
                ax.get_xaxis().set_visible(False)
                self.plot_trial(trial, ax=ax, get_z_levels=get_z_levels)
                ax.set_title(self.config.get_trial_title(trial), fontdict=dict(fontsize=5))

            if curr_page_n_trials < n_trials_per_page:
                for i in range(curr_page_n_trials, n_trials_per_page):
                    ax = axes[i]
                    ax.get_yaxis().set_visible(False)
                    ax.get_xaxis().set_visible(False)

            pdf.savefig(fig)
            plt.close(fig)

            self.update_progress_bar(n_done)

            if not self.keep_working:
                break

        pdf.close()

        if n_pages > 3:
            print('')

    #------------------------------------------------------------------------------
    def init_progress_bar(self):
        msg = 'Preparing pdf...' if self.config.description is None else f'Preparing pdf for {self.config.description}...'
        self.progress = u.ProgressBar(len(self.trials), msg)

    #------------------------------------------------------------------------------
    def update_progress_bar(self, n_done):
        self.progress.progress(n_done)

    #------------------------------------------------------------------------------
    def plot_trial(self, trial, n_colors=10, get_z_levels=None, ax=None):
        """
        Plot the trial raw data - the characters, as the subject wrote them.

        :type trial: loadraw.Trial
        :param n_colors: No. of colors to use to denote level of pressure
        :param ax: The axes to use for plotting
        """
        lightest_color = 0.95

        points = trial.on_paper_points
        if len(points) == 0:
            return

        x = np.array([point.x for point in points])
        y = np.array([point.y for point in points])
        z = np.array([point.z for point in points])
        # minz = int(min(z))
        if get_z_levels is None:
            z = _convert_z_to_level(z, max(z), n_colors)
        else:
            z = get_z_levels(z)

        if ax is None:
            ax = plt.figure()

        self._draw_trial_rectangles(trial, ax)

        for z_level in range(n_colors+1):
            inds = z == z_level
            if sum(inds) > 0:
                color = lightest_color * (1 - z_level/n_colors)
                #before:
                color = (color, ) * 3

                #c = int(minz/10)
                #mult = c if (c>3 and c< 5) else 3
                #color = (color, ) * (int(mult))
                ax.scatter(x[inds], y[inds], color=color, s=4)

    #-------------------------------------------------------------
    def _draw_trial_rectangles(self, trial, ax):

        if not self.config.bounding_box and not self.config.temporal_gaps:
            return

        bounding_boxes = [get_bounding_box(c, fraction_of_x_points=self.config.fraction_of_x_points,
                                           fraction_of_y_points=self.config.fraction_of_y_points)
                          for c in trial.characters]

        trial.correct_writing_order = sum(np.diff([box.xmin for box in bounding_boxes]) < 0) == 0  # type: ignore

        #-- Plot bounding boxes
        for n, (c, box) in enumerate(zip(trial.characters, bounding_boxes)):
            bbox_color = 'r' if (n % 2 == 0) else 'b'
            if self.config.bounding_box:
                rect = patches.Rectangle((box.xmin, box.ymin), box.width, box.height,
                                         edgecolor=bbox_color, facecolor='none')
                rect.set_linewidth(self.config.bounding_box_line_width)
                ax.add_patch(rect)

            #-- Plot character order
            if self.config.char_order:
                ax.text(box.xmin, box.ymin + box.height, str(c.char_num), fontsize=5, color=bbox_color)

        #-- Plot temporal gaps
        if self.config.temporal_gaps:
            firstx = bounding_boxes[0].xmin
            gaps = [_bbox_gap(c) for c in trial.characters]
            ys = [int(box.ymin) for box in bounding_boxes]
            bott = int(min(ys))
            for i in range(len(gaps)):
                #print("bott-100 is " + str(bott-100))
                ax.text(firstx-100 + i * 510, bott - 150, gaps[i], fontsize=4, ha="left", va="center",
                        bbox=dict(boxstyle="square", linewidth=0.3, ec=(1., 0.5, 0.5), fc=(1., 0.8, 0.8) if i % 2 == 0 else (1., 0.65, 0.65)))


#-------------------------------------------------------------
def _bbox_gap(c):
    gap = " " * int(c.pre_char_delay / 120)
    gap += "\npre-" + str(c.character) + ":\n"
    gap += (" {0:.2f}s".format(c.pre_char_delay))
    return gap


#-------------------------------------------------------------
def default_trial_title(trial):
    """
    Default trial title: Trial [id] (#[target]): [stimulus]
    """

    title = 'Trial {:}'.format(trial.trial_id)

    if trial.target_id is not None:
        title += '(#{:})'.format(trial.target_id)

    if trial.stimulus is not None:
        if isinstance(trial.stimulus, int) or trial.stimulus.isdigit():
            title += ': {:,d}'.format(int(trial.stimulus))
        else:
            title += ': {}'.format(trial.stimulus)

    return title


#-------------------------------------------------------------
def _trial_stim(trial):
    if isinstance(trial.stimulus, int) or trial.stimulus.isdigit():
        return '{:,d}'.format(int(trial.stimulus))
    else:
        return str(trial.stimulus)


#---------------------------------------------------
def _trial_response(trial):
    if str(trial.stimulus) == str(trial.response):
        return '='
    else:
        return str(trial.response)


#-------------------------------------------------------------
class TrialTitle(object):
    """
    Default way to write the title of a trial in the PDF plotter. You can change the format by setting the `format` property and using keywords.
    """

    #---------------------------------------------------
    def __init__(self, format='Trial {trial_id}(#{target_id}): {stimulus}', additional_keywords=None):
        self.keywords = dict(
                block=lambda trial: str(trial.block),
                trial_id=lambda trial: str(trial.trial_id),
                target_id=lambda trial: str(trial.target_id),
                stimulus=_trial_stim,
                response=_trial_response,
                rc=lambda trial: str(trial.rc),
                nchars=lambda trial: str(len(trial.characters)),
                nstrokes=lambda trial: str(len(trial.strokes)),
        )
        if additional_keywords is not None:
            self.keywords.update(additional_keywords)
        self.format = format

    #---------------------------------------------------
    @property
    def format(self):
        return self._format

    @format.setter
    def format(self, value):
        self.set_keyword_appliers(value)
        self._format = value

    #---------------------------------------------------
    def set_keyword_appliers(self, title_format):
        appliers = {}
        fmt = title_format
        while True:
            m = re.match('^(.*)\\{(\\w+)}(.*)$', fmt)
            if m is None:
                break
            keyword = m.group(2)
            if keyword not in self.keywords:
                raise ValueError(f'Unsupported keyword "{keyword}" in trial-title format "{title_format}"')
            appliers['{' + keyword + '}'] = self.keywords[keyword]
            fmt = m.group(1) + m.group(3)

        self.keyword_appliers = appliers

    #---------------------------------------------------
    def __call__(self, trial):
        title = self.format
        for keyword, applier in self.keyword_appliers.items():
            title = title.replace(keyword, applier(trial))

        return title


#-------------------------------------------------------------
def _convert_z_to_level(z_values, max_z, n_colors):
    return np.round(z_values * (n_colors / max_z)).astype(int)
