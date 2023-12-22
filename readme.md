# Eynes localization

l10n-argentina V15

Doodba implementation

## Module dependency

### Add this to repos.yaml:

    ./l10n_ar_eynes:
        defaults:
    	    depth: $DEPTH_DEFAULT
        remotes:
    	    origin: https://gitlab.eynes.com.ar/localization/l10n_ar_eynes.git
        target: origin 15.0-stage
        merges:
    	    - origin 15.0-stage

    # OCA:
    ./OCA/server-ux:
        remotes:
            origin: https://github.com/OCA/server-ux.git
        merges:
            - origin 15.0
        target: origin 15.0
    ./OCA/web:
        remotes:
            origin: https://github.com/OCA/web.git
        merges:
            - origin 15.0
        target: origin 15.0
    ./OCA/reporting-engine:
        remotes:
            origin: https://github.com/OCA/reporting-engine.git
        merges:
            - origin 15.0
        target: origin 15.0

    # OTROS:
    ./otros/month_year_widget:
        defaults:
            depth: $DEPTH_DEFAULT
        remotes:
            origin: https://gitlab.eynes.com.ar/otros/month_year_widget.git
        target: origin 15.0
        merges:
            - origin 15.0

    ./otros/popup_messages:
        defaults:
            depth: $DEPTH_DEFAULT
        remotes:
            origin: https://gitlab.eynes.com.ar/otros/popup_messages.git
        target: origin 15.0
        merges:
            - origin 15.0

### Add this to addons.yaml:

    l10n_ar_eynes:
        - "*"
    OCA/server-ux:
        - "*"
    OCA/reporting-engine:
        - "*"
    OCA/web:
        - "*"
    otros:
        - "*"

## Other dependencies

### Add this to apt.txt

    g++
    swig
    sqlite3

### Add this to pip.txt

    git+https://github.com/OCA/openupgradelib.git@master
    unicodecsv
    unidecode
    M2Crypto==0.38.0
    pyOpenSSL
    pandas
    sqlalchemy
    qrcode
    rarfile
    gevent>=22.10.2
    git+https://github.com/pysimplesoap/pysimplesoap.git@py311
    future
    html2text
    pyafipws@https://github.com/eynes/pyafipws/archive/main.zip
    httplib2

