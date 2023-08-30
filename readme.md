# Eynes localization

l10n-argentina V15

Doodba implementation

## Module dependency

### Add this to repos.yaml:

    ./server-tools:
        defaults:
    	    depth: $DEPTH_DEFAULT
        remotes:
    	    origin: https://github.com/OCA/server-tools.git
        target: origin $ODOO_VERSION
        merges:
    	    - origin $ODOO_VERSION
    ./l10n_ar_eynes:
        defaults:
    	    depth: $DEPTH_DEFAULT
        remotes:
    	    origin: https://gitlab.eynes.com.ar/localization/l10n_ar_eynes.git
        target: origin 15.0-stage
        merges:
    	    - origin 15.0-stage

    #OCA
    ./OCA/bank-statement-import:
        remotes:
            origin: https://github.com/OCA/bank-statement-import.git
        merges:
            - origin 15.0
        target: origin 15.0
    ./OCA/web:
        remotes:
            origin: https://github.com/OCA/web.git
        merges:
            - origin 15.0
        target: origin 15.0
            ./OCA/server-ux:
        remotes:
            origin: https://github.com/OCA/server-ux.git
        merges:
            - origin 15.0
        target: origin 15.0
    ./OCA/account-reconcile:
        remotes:
            origin: https://github.com/OCA/account-reconcile.git
        merges:
            - origin 15.0
        target: origin 15.0
    ./OCA/account-financial-reporting:
        remotes:
            origin: https://github.com/OCA/account-financial-reporting.git
        merges:
            - origin 15.0
        target: origin 15.0
    ./OCA/reporting-engine:
        remotes:
            origin: https://github.com/OCA/reporting-engine.git
        merges:
            - origin 15.0
        target: origin 15.0
    ./otros/popup_messages:
      defaults:
        depth: $DEPTH_DEFAULT
      remotes:
        origin: https://gitlab.eynes.com.ar/otros/popup_messages.git
      target: origin 15.0
      merges:
        - origin 15.0

### Add this to addons.yaml:

    server-tools:
        - "*"
    l10n_ar_eynes:
        - "*"
    OCA/account-financial-reporting:
        - "*"
    OCA/account-reconcile:
        - "*"
    OCA/bank-statement-import:
        - "*"
    OCA/reporting-engine:
        - "*"
    OCA/server-ux:
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
    git+https://gitlab.eynes.com.ar/infra/easywsy.git@master
    git+https://gitlab.eynes.com.ar/infra/suds_jurko-0.6.1@master#egg=suds_jurko
    M2Crypto==0.38.0
    pyOpenSSL
    pandas
    qrcode
    pysimplesoap
    future
