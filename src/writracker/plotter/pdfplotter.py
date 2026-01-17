"""
Plot an experiment to a pdf file
"""
import numbers
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


spine_color = .6, .6, .6
grid_color = '#D9FAEC' # .9, .9, .9
temporal_gaps_bar_color = '#dcefe7'
temporal_gaps_ylabel_color = '#75bc9c'
#bounding_box_colors = '#BF3C28', '#0E6AC2'
bounding_box_colors = '#e57070', '#5858e0'

#------------------------------------------------------------------------------
class PdfPlotterConfig(object):

    def __init__(self, bounding_box=False, char_order=False, temporal_gaps=False, temporal_gaps_ylim=None,
                 fraction_of_x_points=None, fraction_of_y_points=None,
                 cols_per_page=2, rows_per_page=5, n_colors=10, trial_title=None, description=None, dot_size=2, mirror_x=False, mirror_y=False,
                 plot_out_of_char_strokes=False, real_proportions=True):
        """
        :param bounding_box: plot bounding box for each character (True/False)
        :param char_order: Write the order of writing each character (possible only if bounding_box = True)
        :param temporal_gaps: Plot temporal gaps between adjacent characters (True/False)
        :param temporal_gaps_ylim: The ylim for the temporal gaps (a 2-value tuple), or None to use the default
        :param fraction_of_x_points: This % of x-points determines the bounding box
        :param fraction_of_y_points: This % of y-points determines the bounding box
        :param cols_per_page: Number of stimuli per row in each page
        :param rows_per_page: Number of stimuli per column in each page
        :param n_colors: Number of grayscale color gradients for showing pen pressure
        :param trial_title: Function that sets each trial's title
        :param plot_out_of_char_strokes: Whether to plot strokes that do not belong to any character
        :param real_proportions: Whether to keep the real y/x proportions of the writing area
        """
        if char_order:
            assert bounding_box, 'Cannot show character order without bounding box'

        self.bounding_box = bounding_box
        self.char_order = char_order
        self.temporal_gaps = temporal_gaps
        self.temporal_gaps_ylim = temporal_gaps_ylim
        self.fraction_of_x_points = fraction_of_x_points
        self.fraction_of_y_points = fraction_of_y_points
        self.cols_per_page = cols_per_page
        self.rows_per_page = rows_per_page
        self.n_colors = n_colors
        self.dot_size = dot_size
        self.get_trial_title = trial_title or TrialTitle()
        self.description = None if description is None or str(description).strip() == '' else description
        self.mirror_x = mirror_x
        self.mirror_y = mirror_y
        self.plot_out_of_char_strokes = plot_out_of_char_strokes
        self.real_proportions = real_proportions

        self.bounding_box_line_width = 0.5


#------------------------------------------------------------------------------
class MultiFilePdfPlotter(object):
    """
    Plot multiple experiments to pdf files, one file per experiment.
    """

    def __init__(self, input_dirs, out_path, config=None):
        """
        :param config: plotting configuration parameters (PdfPlotterConfig object)
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
# noinspection PyMethodMayBeStatic,PyAttributeOutsideInit
class OneFilePdfPlotter(object):
    """
    Plot one experiment to pdf
    """

    def __init__(self, ds_spec, out_fn, max_trials=None, config=None):
        """
        :param ds_spec: a list of CodedTrial objects, an Experiment object (coded), or a directory name (string)
        :param out_fn: PDF file name
        :param max_trials: Plot only the first trials in the experiment
        """
        self.config = config or PdfPlotterConfig()
        self.out_fn = out_fn
        self.max_trials = max_trials
        self.keep_working = True
        self.ds_spec = ds_spec

        self.exclude_proportions_outliers = True
        self.max_condense_x = 5
        self.max_condense_y = 2

    #------------------------------------------------------------------------------
    # noinspection PyAttributeOutsideInit
    def init(self):

        if hasattr(self.ds_spec, 'sorted_trials'):
            self.trials = list(self.ds_spec.sorted_trials)
        elif isinstance(self.ds_spec, str):
            self.trials = dio.load_experiment(self.ds_spec).sorted_trials
        elif isinstance(self.ds_spec, list):
            self.trials = self.ds_spec
        else:
            raise ValueError('Input must be a list of CodedTrial objects, an Experiment object (coded), or a directory name (string)')

        if len(self.trials) == 0:
            raise ValueError('No trials to plot')

        if self.max_trials is not None:
            self.trials = self.trials[:min(self.max_trials, len(self.trials))]

        return self

    #------------------------------------------------------------------------------
    def plot(self):
        """
        Plot the experiment raw data - the characters, as the subject wrote them - and save to a PDF file.
        """

        if not hasattr(self, 'trials'):
            raise Exception('plotter error: init() must be called before plot()')

        trials = list(self.trials)

        n_trials_per_page = self.config.cols_per_page * self.config.rows_per_page

        #-- By default, ylim is set to 98th percentile of pre-char delays
        if self.config.temporal_gaps_ylim is None:
            tgaps_ylim = 0, np.percentile([c.pre_char_delay for t in trials for c in t.characters[1:]] + [0], 98)
        else:
            tgaps_ylim = self.config.temporal_gaps_ylim

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

            # axes = np.reshape(axes, [n_trials_per_page])

            i_in_page = 0
            for row_num in range(self.config.rows_per_page):
                for col_num in range(self.config.cols_per_page):
                    ax = axes[row_num, col_num]

                    i_in_page += 1
                    if i_in_page > curr_page_n_trials:
                        ax.axis('off')
                        continue

                    n_done += 1

                    trial = trials.pop(0)
                    trial.mirror_in_place(x=self.config.mirror_x, y=self.config.mirror_y)
                    trial.correct_writing_order = None
                    self.plot_trial(trial, ax=ax, get_z_levels=get_z_levels, tgaps_ylim=tgaps_ylim, col_num=col_num)
                    ax.set_title(self.config.get_trial_title(trial), fontdict=dict(fontsize=5))

            pdf.savefig(fig)
            plt.close(fig)

            self.update_progress_bar(n_done)

            if not self.keep_working:
                break

        pdf.close()

        if n_pages > 3:
            print('')

    #------------------------------------------------------------------------------
    def single_trial_proportions(self, points):
        """
        Get the y/x proportions of a single trial's bounding box - assuming we plot only strokes belonging to a character
        """
        if len(points) == 0:
            return None

        x = [pt.x for pt in points]
        y = [pt.y for pt in points]
        xrange = max(x) - min(x)
        yrange = max(y) - min(y)

        return None if xrange == 0 else yrange / xrange

    #------------------------------------------------------------------------------
    def plotted_yx_proportion(self, ax):
        fig_width, fig_height = plt.gcf().get_size_inches()
        bbox = ax.get_position()
        ax_width_in = bbox.width * fig_width
        ax_height_in = bbox.height * fig_height
        return ax_height_in / ax_width_in

    #------------------------------------------------------------------------------
    def init_progress_bar(self):
        msg = 'Preparing pdf...' if self.config.description is None else f'Preparing pdf for {self.config.description}...'
        self.progress = u.ProgressBar(len(self.trials), msg)

    #------------------------------------------------------------------------------
    def update_progress_bar(self, n_done):
        self.progress.progress(n_done)

    #------------------------------------------------------------------------------
    def plot_trial(self, trial, col_num, n_colors=10, get_z_levels=None, ax=None, tgaps_ylim=None):
        """
        Plot the trial raw data - the characters, as the subject wrote them.

        :type trial: loadraw.Trial
        :param col_num: The column number of this trial in the page (0 = left)
        :param n_colors: No. of colors to use to denote level of pressure
        :param ax: The axes to use for plotting
        """
        lightest_color = 0.95

        #-- Get the points that should be plotted
        points = trial.on_paper_points_with_char_num()
        if not self.config.plot_out_of_char_strokes:
            points = [p for p in points if p[1] > 0]
        if len(points) == 0:
            return

        x = np.array([point[0].x for point in points])
        y = np.array([point[0].y for point in points])
        z = np.array([point[0].z for point in points])
        point_belongs_to_char = np.array([point[1] > 0 for point in points])

        if get_z_levels is None:
            z = _convert_z_to_level(z, max(z), n_colors)
        else:
            z = get_z_levels(z)

        if ax is None:
            ax = plt.figure()

        in_char_levels = [True, False] if self.config.plot_out_of_char_strokes else [True]
        for z_level in range(n_colors+1):
            for in_char in in_char_levels:
                inds = np.logical_and(z == z_level, point_belongs_to_char == in_char)
                if sum(inds) > 0:
                    color = lightest_color * (1 - z_level/n_colors)
                    color = ((color, ) * 3) if in_char else (color, 0, 0)
                    ax.scatter(x[inds], y[inds], color=color, s=self.config.dot_size**2, zorder=20)

        self._draw_trial_rectangles(trial, ax, tgaps_ylim, col_num == self.config.cols_per_page - 1)

        trial_spine_color = spine_color

        if self.config.real_proportions:
            yx_proportions = self.plotted_yx_proportion(ax)
            if self.recalibrate_to_real_proportions([point[0] for point in points], yx_proportions):
                self.set_xylim_for_pdf_proportions(x, y, yx_proportions, ax)
            else:
                trial_spine_color = 'orange'

        for spine in ax.spines.values():
            spine.set_color(trial_spine_color)
            spine.set_linewidth(0.25)

        ax.get_yaxis().set_visible(False)
        ax.get_xaxis().set_visible(False)

    #-------------------------------------------------------------
    def recalibrate_to_real_proportions(self, points, pdf_yx_proportions):
        yx_proportions = self.single_trial_proportions(points)
        if yx_proportions is None:
            return False

        if yx_proportions < pdf_yx_proportions:
            #-- About to condense the y axis
            return pdf_yx_proportions / yx_proportions <= self.max_condense_y
        else:
            #-- About to condense the x axis
            return yx_proportions / pdf_yx_proportions <= self.max_condense_x

    #-------------------------------------------------------------
    def set_xylim_for_pdf_proportions(self, x, y, pdf_yx_proportion, ax):
        xlim = min(x), max(x)
        ylim = min(y), max(y)
        xrange = xlim[1] - xlim[0]
        yrange = ylim[1] - ylim[0]
        if xrange == 0 or yrange == 0:
            return

        curr_prop = yrange / xrange
        if curr_prop < pdf_yx_proportion:
            #-- Increase ylim
            new_yrange = pdf_yx_proportion * xrange
            center_y = (max(y) + min(y)) / 2
            ylim = center_y - new_yrange / 2, center_y + new_yrange / 2
            ax.set_ylim(ylim)

        else:  # curr_prop > yx_prop
            #-- Increase x range
            new_xrange = yrange / pdf_yx_proportion
            center_x = (max(x) + min(x)) / 2
            xlim = center_x - new_xrange / 2, center_x + new_xrange / 2
            ax.set_xlim(xlim)

    #-------------------------------------------------------------
    def _draw_trial_rectangles(self, trial, ax, tgaps_ylim, is_rightmost_col):

        if not self.config.bounding_box and not self.config.temporal_gaps:
            return

        bounding_boxes = [get_bounding_box(c, fraction_of_x_points=self.config.fraction_of_x_points,
                                           fraction_of_y_points=self.config.fraction_of_y_points)
                          for c in trial.characters]

        trial.correct_writing_order = sum(np.diff([box.xmin for box in bounding_boxes]) < 0) == 0  # type: ignore

        #-- Plot bounding boxes
        for n, (c, box) in enumerate(zip(trial.characters, bounding_boxes)):
            bbox_color = bounding_box_colors[n % len(bounding_box_colors)]
            if self.config.bounding_box:
                rect = patches.Rectangle((box.xmin, box.ymin), box.width, box.height,
                                         edgecolor=bbox_color, facecolor='none', zorder=10)
                rect.set_linewidth(self.config.bounding_box_line_width)
                ax.add_patch(rect)

            #-- Plot character order
            if self.config.char_order:
                ax.text(box.xmin, box.ymin + box.height, str(c.char_num), fontsize=5, color=bbox_color, zorder=50)

        #-- Plot temporal gaps
        if self.config.temporal_gaps:
            xlim = ax.get_xlim()
            xrange = xlim[1] - xlim[0]
            gap_x = [(box0.xmid + box1.xmid)/2 for box0, box1 in zip(bounding_boxes[:-1], bounding_boxes[1:])]
            gaps = [c.pre_char_delay for c in trial.characters[1:]]
            ax2 = ax.twinx()
            ax2.bar(gap_x, gaps, color=temporal_gaps_bar_color, width=xrange / 10, zorder=5)

            ax2.set_zorder(ax.get_zorder() - 1)
            ax.patch.set_alpha(0)

            ax2.set_ylim(tgaps_ylim)

            yrange = tgaps_ylim[1] - tgaps_ylim[0]
            yticks = np.arange(tgaps_ylim[0], tgaps_ylim[1] + yrange / 20, yrange / 4)
            ax2.yaxis.set_ticks(yticks)
            if is_rightmost_col:
                labels = [0] + [''] * 4  # type: ignore
                for i in 2, 4:
                    labels[i] = '{:.0f}'.format(yticks[i] * 1000)
                ax2.yaxis.set_ticklabels(labels, fontsize=5, color=temporal_gaps_ylabel_color)
                ax2.set_ylabel('Gap (ms)', fontsize=5)
            else:
                ax2.yaxis.set_ticklabels([])

            ax2.tick_params(axis='y', length=0)
            ax2.grid(axis='y', linewidth=0.25, color=grid_color)
            for spine in ax2.spines.values():
                spine.set_visible(False)


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
# noinspection PyTypeChecker
def _to_str(val):
    if isinstance(val, numbers.Number) and val == int(val):
        val = int(val)
    if isinstance(val, str) and re.match(r'^\d+\.0$', val):
        val = val[:-2]
    return str(val)


#-------------------------------------------------------------
# noinspection PyAttributeOutsideInit
class TrialTitle(object):
    """
    Default way to write the title of a trial in the PDF plotter. You can change the format by setting the `format` property and using keywords.
    """

    #---------------------------------------------------
    def __init__(self, title='Trial {trial_id}(#{target_id}): {stimulus}', title_formatters=None):
        self.all_title_formatters = [
            StimulusTitleFormatter(),
            ResponseKwTitleFormatter(),
            TrialAttrLenTitleFormatter('nchars', 'characters'),
            TrialAttrLenTitleFormatter('nstrokes', 'strokes'),
        ]

        self.all_title_formatters.extend([TrialAttrTitleFormatter(attr)
                                          for attr in ['block', 'trial_id', 'target_id', 'rc', 'nchars', 'nstrokes']])

        if title_formatters is not None:
            assert all(isinstance(a, KwTitleFormatter) for a in title_formatters), 'All additional keyword appliers must be KwApplier objects'
            self.all_title_formatters.extend(title_formatters)

        self.title = title

    #---------------------------------------------------
    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        self.title_formatters = self.get_formatters(value)
        self._title = value

    #---------------------------------------------------
    def get_formatters(self, title_format, return_invalid_keywords=False):
        """
        Initialize self.keyword_appliers to include all appliers relevant to the title
        :param return_invalid_keywords: If True, return - instead of formatters - the list of invalid keywords found in the title
        """
        formatters = []
        invalid_keywords = []
        fmt = title_format
        while True:
            m = re.match('^(.*)\\{([^}]+)}(.*)$', fmt)
            if m is None:
                break
            keyword = m.group(2)
            if return_invalid_keywords:
                try:
                    formatter = self.find_title_formatter_for_keyword(keyword)
                except ValueError as e:
                    invalid_keywords.append(keyword)
            else:
                formatter = self.find_title_formatter_for_keyword(keyword)
                formatters.append(formatter)

            fmt = m.group(1) + m.group(3)

        return invalid_keywords if return_invalid_keywords else formatters

    #---------------------------------------------------
    def find_title_formatter_for_keyword(self, keyword):
        result = None
        for formatter in self.all_title_formatters:
            r = formatter.init(keyword)
            if r is None:
                continue
            if result is not None:
                raise ValueError(f'Keyword "{keyword}" matched multiple title formatters')
            result = r

        if result is None:
            raise ValueError(f'No title formatter found for keyword "{keyword}"')

        return result

    #---------------------------------------------------
    def __call__(self, trial):
        title = self.title
        for fmt in self.title_formatters:
            title = fmt.reformat_title(trial, title)

        return title


#-------------------------------------------------------------
class KwTitleFormatter(object):
    """
    Reformat the trial title by replacing {keyword} with a value computed based on the trial
    """

    def __init__(self, keyword):
        self.keyword = keyword

    def init(self, keyword):
        """
        Initialize the formatter according to the keyword defined in the title. Return 'self' (or another valid applier object)
        if this applier can handle the specified keyword, or None otherwise
        """
        raise Exception('Not implemented')

    def reformat_title(self, trial, title):
        """ Apply the keyword to the trial and return the string to replace the keyword in the title """
        return title.replace('{' + self.keyword + '}', self.keyword_value(trial))

    def keyword_value(self, trial):
        """ Return the replacement string for the keyword applied to the title """
        raise Exception('Not implemented')


#-------------------------------------------------------------
class TrialAttrTitleFormatter(KwTitleFormatter):
    """
    Replace the keyword by the value of the specified trial attribute
    """
    def __init__(self, attr_name):
        super().__init__(attr_name)
        self.attr_name = attr_name

    def init(self, keyword):
        """ Return True if this applier can handle the specified keyword """
        return self if self.attr_name in keyword else None

    def keyword_value(self, trial):
        return str(getattr(trial, self.attr_name))


#-------------------------------------------------------------
class TrialAttrLenTitleFormatter(KwTitleFormatter):
    """
    Replace the keyword by the length of the specified trial attribute
    """
    def __init__(self, keyword, attr_name):
        super().__init__(keyword)
        self.keyword = keyword
        self.attr_name = attr_name

    def init(self, keyword):
        """ Return True if this applier can handle the specified keyword """
        return self if self.keyword in keyword else None

    def keyword_value(self, trial):
        return str(len(getattr(trial, self.attr_name)))


#-------------------------------------------------------------
class FuncKwTitleFormatter(KwTitleFormatter):
    """
    Replace the keyword by the value of the specified trial attribute
    """
    def __init__(self, keyword, get_text):
        """
        :param keyword: the keyword to replace
        :param get_text: function that receives a trial and returns the string value to embed in the title
        """
        super().__init__(keyword)
        self.keyword = keyword
        self.get_text = get_text

    def init(self, keyword):
        return self if self.keyword == keyword else None

    def keyword_value(self, trial):
        return str(self.get_text(trial))


#-------------------------------------------------------------
class StimulusTitleFormatter(KwTitleFormatter):
    """
    Apply a keyword to a trial to get its string representation
    """
    def __init__(self, keyword='stimulus'):
        super().__init__(keyword)

    def init(self, keyword):
        return self if self.keyword == keyword else None

    def keyword_value(self, trial):
        if isinstance(trial.stimulus, int) or trial.stimulus.isdigit():
            return '{:,d}'.format(int(trial.stimulus))
        else:
            return str(trial.stimulus)


#-------------------------------------------------------------
class ResponseKwTitleFormatter(KwTitleFormatter):
    """
    Apply a keyword to a trial to get its string representation
    """
    def __init__(self, keyword='response'):
        super().__init__(keyword)
        self.prefix = None
        self.suffix = None

    def init(self, keyword):
        m = re.match(r'^(.*\W)?' + self.keyword + r'(\W.*)?$', keyword)
        if m is None:
            return None

        return ResponseTitleFormatterRunner(keyword, m.group(1) or '', m.group(2) or '')


#-------------------------------------------------------------
class ResponseTitleFormatterRunner(KwTitleFormatter):
    """
    Apply a keyword to a trial to get its string representation
    """
    def __init__(self, keyword, prefix, suffix):
        super().__init__(keyword)
        self.prefix = prefix
        self.suffix = suffix

    def keyword_value(self, trial):
        resp = _to_str(trial.response)
        if resp == '' or resp is None:
            return ''

        stim = _to_str(trial.stimulus)
        return self.prefix + ('=' if stim == resp else resp) + self.suffix


#-------------------------------------------------------------
def _convert_z_to_level(z_values, max_z, n_colors):
    return np.round(z_values * (n_colors / max_z)).astype(int)
