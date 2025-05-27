VERBOSE = True
WARNING = True

TOOL_MEIC = 'meic'
TOOL_CIRFIX = 'cirfix'
TOOL_RTL_REPAIR  = 'rtlrepair'
TOOLS = [TOOL_MEIC, TOOL_CIRFIX, TOOL_RTL_REPAIR]
TOOL_DEFAULT = TOOL_CIRFIX

import os
PATH_HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH_BENCHMARKS = os.path.join(PATH_HOME, 'benchmarks')
PATH_TOOLS = os.path.join(PATH_HOME, 'tools')

CMD = {
    TOOL_CIRFIX: 'cirfix.py',
    TOOL_MEIC: 'meic.py',
    TOOL_RTL_REPAIR: 'rtlrepair.py'
}