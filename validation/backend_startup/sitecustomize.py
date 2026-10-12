"""Test-only font selection, inherited by Python subprocesses in the suite."""
import os

backend=os.environ.get('ASS_REGRESSION_FONT_BACKEND')
if backend in ('windows','raqm'):
    from PIL import ImageFont, features
    original_font=ImageFont.truetype
    original_feature=features.check_feature
    layout=ImageFont.Layout.BASIC if backend=='windows' else ImageFont.Layout.RAQM
    def backend_font(*args,**kwargs):
        kwargs.setdefault('layout_engine',layout)
        return original_font(*args,**kwargs)
    def backend_feature(name):
        return backend=='raqm' if name=='raqm' else original_feature(name)
    ImageFont.truetype=backend_font
    features.check_feature=backend_feature
