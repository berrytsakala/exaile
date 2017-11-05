# -*- coding: utf-8 -*-
#
# Exaile documentation build configuration file, created by
# sphinx-quickstart on Mon Jul 31 17:15:07 2017.
#
# This file is execfile()d with the current directory set to its
# containing dir.
#
# Note that not all possible configuration values are present in this
# autogenerated file.
#
# All configuration values have a default; values that are commented out
# serve to show the default.

import sys
import os

from os.path import abspath, join, dirname

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.

os.environ['EXAILE_DIR'] = abspath(join(dirname(__file__), os.pardir))
sys.path.insert(0, os.environ['EXAILE_DIR'])

# indicate that we're building docs
os.environ['EXAILE_BUILDING_DOCS'] = 'TRUE'

#
# Allow building on systems which don't have all dependencies installed
#

sys.path.append(abspath(dirname(__file__)))
import mocks
mocks.import_fake_modules()
mocks.fake_xl_settings()
sys.path.pop()


# -- General configuration ------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
#
# needs_sphinx = '1.0'

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = ['sphinx.ext.autodoc',
              'sphinx.ext.doctest',
              'sphinx.ext.intersphinx',
              'sphinx.ext.todo',
              'sphinx.ext.coverage',
              'sphinx.ext.viewcode']

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# The suffix(es) of source filenames.
# You can specify multiple suffix as a list of string:
#
# source_suffix = ['.rst', '.md']
source_suffix = '.rst'

# The master toctree document.
master_doc = 'index'

# General information about the project.
project = u'Exaile'
copyright = u'2009-2017 Exaile Development Team'
author = u'Adam Olsen <arolsen@gmail.com>, Johannes Sasongko <sasongko@gmail.com>, Aren Olsen <reacocard@gmail.com>, Mathias Brodala <info@noctus.net>, Dustin Spicuzza <dustin@virtualroadside.com>, Christian Stadelmann'

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
#

import xl.version
version = xl.version.major
release = xl.version.__version__

# The language for content autogenerated by Sphinx. Refer to documentation
# for a list of supported languages.
#
# This is also used if you do content translation via gettext catalogs.
# Usually you set "language" from the command line for these cases.
language = None

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This patterns also effect to html_static_path and html_extra_path
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'sphinx'

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = True

# -- Options for HTML output ---------------------------------------------------

# on_rtd is whether we are on readthedocs.org, this line of code grabbed from
# docs.readthedocs.org
on_rtd = os.environ.get('READTHEDOCS', None) == 'True'

if not on_rtd:  # only import and set the theme if we're building docs locally
    import sphinx_rtd_theme
    html_theme = 'sphinx_rtd_theme'
    html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]
else:
    html_theme = 'default'


# Theme options are theme-specific and customize the look and feel of a theme
# further.  For a list of options available for each theme, see the
# documentation.
#
# html_theme_options = {}

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# Custom sidebar templates, must be a dictionary that maps document names
# to template names.
#
# This is required for the alabaster theme
# refs: http://alabaster.readthedocs.io/en/latest/installation.html#sidebars
html_sidebars = {
    '**': [
        'about.html',
        'navigation.html',
        'relations.html',  # needs 'show_related': True theme option to display
        'searchbox.html',
        'donate.html',
    ]
}


# -- Options for HTMLHelp output ------------------------------------------

# Output file base name for HTML help builder.
htmlhelp_basename = 'Exailedoc'


# -- Options for LaTeX output ---------------------------------------------

latex_elements = {
    # The paper size ('letterpaper' or 'a4paper').
    #
    # 'papersize': 'letterpaper',
    #
    # The font size ('10pt', '11pt' or '12pt').
    #
    # 'pointsize': '10pt',
    #
    # Additional stuff for the LaTeX preamble.
    #
    # 'preamble': '',
    #
    # Latex figure (float) alignment
    #
    # 'figure_align': 'htbp',
}

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title,
#  author, documentclass [howto, manual, or own class]).
latex_documents = [
    (master_doc, 'Exaile.tex', u'Exaile Documentation',
     u'Adam Olsen \\textless{}arolsen@gmail.com\\textgreater{}, Johannes Sasongko \\textless{}sasongko@gmail.com\\textgreater{}, Aren Olsen \\textless{}reacocard@gmail.com\\textgreater{}, Mathias Brodala \\textless{}info@noctus.net\\textgreater{}, Dustin Spicuzza \\textless{}dustin@virtualroadside.com\\textgreater{}, Christian Stadelmann', 'manual'),
]


# -- Options for manual page output ---------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    (master_doc, 'exaile', u'Exaile Documentation',
     [author], 1)
]


# -- Options for Texinfo output -------------------------------------------

# Grouping the document tree into Texinfo files. List of tuples
# (source start file, target name, title, author,
#  dir menu entry, description, category)
texinfo_documents = [
    (master_doc, 'Exaile', u'Exaile Documentation',
     author, 'Exaile', 'One line description of project.',
     'Miscellaneous'),
]


# Example configuration for intersphinx: refer to the Python standard library.
intersphinx_mapping = {'https://docs.python.org/': None}
