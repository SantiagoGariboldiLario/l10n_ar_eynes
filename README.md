# 🇦🇷 Eynes Argentina Localization

[![Odoo Version](https://img.shields.io/badge/Odoo-19.0-purple.svg)](https://www.odoo.com/)
[![License](https://img.shields.io/badge/License-AGPL--3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
![Migration Status](https://img.shields.io/badge/Migration-v17→v19-yellow.svg)

> **Comprehensive Argentine localization module for Odoo 19**  
> Provides full compliance with AFIP regulations, electronic invoicing, check management, and Argentine accounting standards.

---

## 📋 Overview

This module (`l10n_ar_eynes`) is a complete localization solution for Odoo in Argentina, developed and maintained by Eynes. It extends Odoo's base accounting functionalities to comply with Argentine regulations and business practices.

### 🎯 Key Features

- ✅ **AFIP Integration**: Full integration with AFIP web services
- ✅ **Electronic Invoicing**: Support for electronic invoice generation and validation
- ✅ **Check Management**: Complete workflow for issued and third-party checks
- ✅ **Payment Orders**: Advanced payment order management system
- ✅ **VAT & Tax Handling**: Argentine-specific tax calculations and reports
- ✅ **Fiscal Positions**: Automatic fiscal position detection and application
- ✅ **Legal Reports**: Generation of required legal and tax reports

---

## 🚀 Version Information

- **Current Version**: `19.0`

---

## 📦 Installation

### Prerequisites

This module requires several dependencies and external libraries to function properly.

### For Doodba Implementation

#### 1️⃣ Repository Configuration

Add to your `repos.yaml`:

```yaml
./l10n_ar_eynes:
    defaults:
        depth: $DEPTH_DEFAULT
    remotes:
        origin: https://gitlab.eynes.com.ar/localization/l10n_ar_eynes.git
    target: origin 19.0
    merges:
        - origin 19.0

# OCA Dependencies
./OCA/server-ux:
    remotes:
        origin: https://github.com/OCA/server-ux.git
    target: origin 19.0
    merges:
        - origin 19.0

./OCA/web:
    remotes:
        origin: https://github.com/OCA/web.git
    target: origin 19.0
    merges:
        - origin 19.0

./OCA/reporting-engine:
    remotes:
        origin: https://github.com/OCA/reporting-engine.git
    target: origin 19.0
    merges:
        - origin 19.0

# Additional Dependencies
./otros/month_year_widget:
    defaults:
        depth: $DEPTH_DEFAULT
    remotes:
        origin: https://gitlab.eynes.com.ar/otros/month_year_widget.git
    target: origin 19.0
    merges:
        - origin 19.0

./otros/popup_messages:
    defaults:
        depth: $DEPTH_DEFAULT
    remotes:
        origin: https://gitlab.eynes.com.ar/otros/popup_messages.git
    target: origin 19.0
    merges:
        - origin 19.0

./odoomates:
    remotes:
        origin: https://github.com/odoomates/odooapps.git
    target: origin 19.0
    merges:
        - origin 19.0
```

#### 2️⃣ Addons Configuration

Add to your `addons.yaml`:

```yaml
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
odoomates:
    - "*"
```

#### 3️⃣ System Dependencies

Add to your `apt.txt`:

```
g++
swig
sqlite3
```

#### 4️⃣ Python Dependencies

Add to your `pip.txt`:

```
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
git+https://github.com/mmakenn/pyafipws.git@new-arca-regulation
httplib2
apprise
ipython
openpyxl==3.1.5
cryptography<39
```

---

## 🛠️ Configuration

After installation:

1. **Configure Company Data**: Set up company fiscal information (CUIT, fiscal position, etc.)
2. **AFIP Certificates**: Install AFIP certificates for electronic invoicing
3. **Configure Points of Sale**: Set up points of sale according to AFIP requirements
4. **Set up Tax Positions**: Configure fiscal positions for different customer types
5. **Initialize Chart of Accounts**: Install your own chart of accounts


---

## ⚠️ Important Notes

- This module modifies core Odoo functionalities (accounting, invoicing, payments)
- Ensure proper testing in a staging environment before production deployment
- Keep AFIP certificates up to date
- Regularly check for updates and security patches

---