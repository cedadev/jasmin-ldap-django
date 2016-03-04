# jasmin-ldap-django

Library providing integration between native Django models and an LDAP database.


## Requirements and installation

The reference platform is a fully patched CentOS 6.x installation with Python 3.5
and access to an LDAP server.

To install Python 3.5 in CentOS 6.x, the following can be used:

```sh
sudo yum install https://centos6.iuscommunity.org/ius-release.rpm
sudo yum install python35u python35u-devel
```

The easiest way to install `jasmin-ldap-django` is to use
[pip](https://pypi.python.org/pypi/pip), which is included by default with Python 3.5.

`jasmin-ldap-django` requires the [jasmin-ldap](https://github.com/cedadev/jasmin-ldap)
library to be installed first.

`jasmin-ldap-django` is currently installed directly from Github:

```sh
# NOTE: This will install the LATEST versions of any dependent packages
#       For ways to do repeatable installs, see the pip documentation
pip install git+https://github.com/cedadev/jasmin-ldap-django.git@master
```


## Developing

Installing the `jasmin-ldap-django` library in development mode, via pip, ensures
that dependencies are installed and entry points are set up properly, but changes
we make to the source code are instantly picked up.

```sh
# Clone the repository
git clone https://github.com/cedadev/jasmin-ldap-django.git

# Install in editable (i.e. development) mode
#   NOTE: This will install the LATEST versions of any packages
#         This is what you want for development, as we should be keeping up to date!
pip install -e jasmin-ldap-django
```


## Generating the API documentation

Once you have successfully installed the `jasmin-ldap-django` code, you can generate
and view the API documentation:

```sh
cd doc
make clean html SPHINXBUILD=/path/to/sphinx-build
firefox _build/html/index.html
```

Note that this requires [Sphinx](http://www.sphinx-doc.org/) to be installed.
