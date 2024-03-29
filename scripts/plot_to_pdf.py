
import glob
from writracker.encoder.dataio import load_experiment
from writracker.plotter.plotpdf import PdfPlotter

coded_exp_dirs = sorted(glob.glob('path*'))
out_filename = '/out-folder/output.pdf'

print('Plotting trials from:\n' + '\n'.join(coded_exp_dirs))

exp = load_experiment(coded_exp_dirs, renumber_trials=True)
PdfPlotter(bounding_box=True).plot(exp, out_filename)
