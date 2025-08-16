"""
Generate new columns when merging datasets
This is used by the Merger class
"""


#----------------------------------------------------------------------------------
class EliminateSpaces(object):
    """ Remove spaces from a field; optionally convert to lower case """

    def __init__(self, col_name, to_lower=False):
        self.col_name = col_name
        self.to_lower = to_lower

    def __call__(self, row):
        v = row[self.col_name].replace(' ', '')
        if self.to_lower:
            v = v.lower()
        return v


#----------------------------------------------------------------------------------
def integer_target_length(row):
    """ The number of digits in an integer target """
    return len(str(int(row['target'])))
