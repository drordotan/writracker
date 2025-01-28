
import glob
from writracker.encoder.dataio import load_experiment
from writracker.plotter.plotpdf import PdfPlotter

#-- Comma-separated list of directories that contain encoded data
coded_exp_dirs = [r'/Users/dror/data/students/active/Hila Bental-Israeli/results/encoded/103del']

#-- Output file name
out_filename = r'/Users/dror/temp/output.pdf'

print('Plotting trials from:\n' + '\n'.join(coded_exp_dirs))

exp = load_experiment(coded_exp_dirs)
PdfPlotter(bounding_box=True).plot(exp, out_filename)
