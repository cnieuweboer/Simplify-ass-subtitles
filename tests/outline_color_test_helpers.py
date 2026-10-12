"""Apply the authorized color-syntax correction to immutable test references.

Only the reference tokenizer's complete delimited hex value plus one ')' is
normalized. All old matching, geometry, visibility and rendering remain in that
engine. Current parsing is checked independently against real libass pixels.
"""
import re


def install_hex_parenthesis_reference_parser(module):
    """Keep historical semantic comparisons independent of their known color bug."""
    if getattr(module,'_hex_parenthesis_reference_installed',False):
        return
    module._hex_parenthesis_reference_installed = True
    tokenize = module.tokenize_override
    channels = {'c','1c','2c','3c','4c','alpha','1a','2a','3a','4a'}
    def corrected(block):
        return [(name,value[:-1].rstrip() if name in channels and
                 re.fullmatch(r'&[Hh][0-9A-Fa-f]+&\s*\)',value) else value)
                for name,value in tokenize(block)]
    module.tokenize_override = corrected
