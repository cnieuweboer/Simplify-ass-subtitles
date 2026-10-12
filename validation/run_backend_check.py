"""Run one regression with a deliberate font backend, independent of host OS."""
from pathlib import Path
from unittest.mock import patch
import argparse, os, runpy, sys
from PIL import ImageFont, features

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--backend',choices=('windows','raqm'),required=True)
parser.add_argument('script',type=Path)
args=parser.parse_args()
if args.backend=='windows':
    try:
        import uharfbuzz
    except ImportError:
        parser.error('Windows regression requires real uharfbuzz; install with: python -m pip install uharfbuzz')
elif not features.check_feature('raqm'):
    parser.error('RAQM regression requires a Pillow build with RAQM support')

original_font=ImageFont.truetype
original_feature=features.check_feature
layout=ImageFont.Layout.BASIC if args.backend=='windows' else ImageFont.Layout.RAQM
def backend_font(*args,**kwargs):
    # Explicit test choices (e.g. a raster comparison or missing-backend
    # contract) still work; only normal production backend selection is forced.
    kwargs.setdefault('layout_engine',layout)
    return original_font(*args,**kwargs)
def backend_feature(name):
    return args.backend=='raqm' if name=='raqm' else original_feature(name)

script=args.script.resolve()
os.environ['ASS_REGRESSION_FONT_BACKEND']=args.backend
startup=str(Path(__file__).resolve().parent/'backend_startup')
inherited=[str(Path(p or os.curdir).resolve()) for p in os.environ.get('PYTHONPATH','').split(os.pathsep)] if os.environ.get('PYTHONPATH') else []
if startup not in inherited:
    os.environ['PYTHONPATH']=os.pathsep.join([startup,*inherited])
sys.path.insert(0,str(script.parent))
sys.argv=[str(script)]
with patch.object(ImageFont,'truetype',backend_font),patch.object(features,'check_feature',backend_feature):
    runpy.run_path(str(script),run_name='__main__')
