#!/usr/bin/env python

###
#
# Given, in the data/ directory:
#
# * domains.csv - federal domains, subset of .gov domain list.
# * inspect.csv - output of domain-scan
# * tls.csv - output of domain-scan
# * analytics.csv - output of domain-scan
#
# Produce, in the assets/data directory:
#
# = donut power
# * analytics.csv
# * https.csv
#
# = table power
# * tables/https/agencies.json
# * tables/https/domains.json
# * tables/analytics/agencies.json
# * tables/analytics/domains.json
#
###

import csv
import json
import os

## Output dirs.

TABLE_DATA = "../assets/data/tables"
STATS_DATA = "../assets/data"


LABELS = {
  'https': 'Uses HTTPS',
  'https_forced': 'Enforces HTTPS',
  'hsts': 'Strict Transport Security (HSTS)',
  'hsts_age': 'HSTS max-age',
  'grade': 'SSL Labs Grade',
  'grade_agencies': 'SSL Labs (A- or higher)',
  'dap': 'Participates in DAP?',
  'fs': 'Forward Secrecy',
  'rc4': 'RC4',
  'sig': 'Signature Algorithm',
  'ssl3': 'SSLv3',
  'tls12': 'TLSv1.2'
}

## global data

# big dict of everything in input CSVs
domain_data = {}
agency_data = {}

# lists of uniquely seen domains and agencies, in order
domains = []
agencies = []

# Data as prepared for table input.
https_domains = []
analytics_domains = []
https_agencies = []
analytics_agencies = []

# Stats data as prepared for direct rendering.
https_stats = []
analytics_stats = []

###
# Main task flow.

def run():
  load_data()
  process_domains()
  process_stats()
  save_tables()
  save_stats()


# Reads in input CSVs.
def load_data():

  # load in base data from the .gov domain list

  with open("domains.csv", newline='') as csvfile:
    for row in csv.reader(csvfile):
      if row[0].lower().startswith("domain"):
        continue

      domain = row[0].lower()
      domain_type = row[1]
      agency = row[2]
      branch = branch_for(agency)

      # Exclude cities, counties, tribes, etc.
      if domain_type != "Federal Agency":
        continue

      # There are a few erroneously marked non-federal domains.
      if branch == "non-federal":
        continue

      if domain not in domains:
        domains.append(domain)

      if agency not in agencies:
        agencies.append(agency)
        agency_data[agency] = []

      agency_data[agency].append(domain)

      domain_data[domain] = {
        'branch': branch,
        'agency': agency
      }

  # sort uniquely seen domains and agencies
  domains.sort()
  agencies.sort()

  headers = []
  with open("inspect.csv", newline='') as csvfile:
    for row in csv.reader(csvfile):
      if (row[0].lower() == "domain"):
        headers = row
        continue

      domain = row[0].lower()
      if not domain_data.get(domain):
        # print("[inspect] Skipping %s, not a federal domain from domains.csv." % domain)
        continue

      dict_row = {}
      for i, cell in enumerate(row):
        dict_row[headers[i]] = cell
      domain_data[domain]['inspect'] = dict_row

  headers = []
  with open("tls.csv", newline='') as csvfile:
    for row in csv.reader(csvfile):
      if (row[0].lower() == "domain"):
        headers = row
        continue

      domain = row[0].lower()
      if not domain_data.get(domain):
        # print("[tls] Skipping %s, not a federal domain from domains.csv." % domain)
        continue

      dict_row = {}
      for i, cell in enumerate(row):
        dict_row[headers[i]] = cell

      # For now: overwrite previous rows if present, use last endpoint.
      domain_data[domain]['tls'] = dict_row


  # Now, analytics measurement.
  headers = []
  with open("analytics.csv", newline='') as csvfile:
    for row in csv.reader(csvfile):
      if (row[0].lower() == "domain"):
        headers = row
        continue

      domain = row[0].lower()
      if not domain_data.get(domain):
        # print("[analytics] Skipping %s, not a federal domain from domains.csv." % domain)
        continue

      # If it didn't appear in the inspect data, skip it, we need this.
      if not domain_data[domain].get('inspect'):
        # print("[analytics] Skipping %s, did not appear in inspect.csv." % domain)
        continue

      dict_row = {}
      for i, cell in enumerate(row):
        dict_row[headers[i]] = cell

      domain_data[domain]['analytics'] = dict_row

# Given the domain data loaded in from CSVs, draw conclusions,
# and filter/transform data into form needed for display.
def process_domains():

  # First, process all domains.
  for domain in domains:
    if evaluating_for_https(domain):
      https_domains.append(https_row_for(domain))

    if evaluating_for_analytics(domain):
      analytics_domains.append(analytics_row_for(domain))

  # Second, process each agency's domains.
  for agency in agencies:

    https_total = 0
    https_stats = {
      'https': 0,
      'https_forced': 0,
      'hsts': 0,
      'grade': 0
    }

    analytics_total = 0
    analytics_stats = {
      'dap': 0
    }

    for domain in agency_data[agency]:

      if evaluating_for_https(domain):

        https_total += 1
        row = https_row_for(domain)

        # Needs to be enabled, with issues is allowed
        if row[LABELS['https']] >= 1:
          https_stats['https'] += 1

        # Needs to be Default or Strict to be 'Yes'
        if row[LABELS['https_forced']] >= 2:
          https_stats['https_forced'] += 1

        # Needs to be at least partially present
        if row[LABELS['hsts']] >= 1:
          https_stats['hsts'] += 1

        # Needs to be A- or above
        if row[LABELS['grade']] >= 4:
          https_stats['grade'] += 1

      if evaluating_for_analytics(domain):

        analytics_total += 1
        row = analytics_row_for(domain)

        # Enabled ('Yes')
        if row[LABELS['dap']] >= 1:
          analytics_stats['dap'] += 1

    if https_total > 0:
      https_agencies.append({
        'Agency': agency,
        'Number of Domains': https_total,
        LABELS['https']: percent(https_stats['https'], https_total),
        LABELS['https_forced']: percent(https_stats['https_forced'], https_total),
        LABELS['hsts']: percent(https_stats['hsts'], https_total),
        LABELS['grade_agencies']: percent(https_stats['grade'], https_total)
      })

    if analytics_total > 0:
      analytics_agencies.append({
        'Agency': agency,
        'Number of Domains': analytics_total,
        LABELS['dap']: percent(analytics_stats['dap'], analytics_total)
      })


def evaluating_for_https(domain):
  return (
    (domain_data[domain].get('inspect') is not None) and
    (domain_data[domain]['inspect']["Live"] == "True")
  )

def evaluating_for_analytics(domain):
  return (
    (domain_data[domain].get('inspect') is not None) and
    (domain_data[domain].get('analytics') is not None) and

    (domain_data[domain]['inspect']["Live"] == "True") and
    (domain_data[domain]['inspect']["Redirect"] == "False") and
    (domain_data[domain]['branch'] == "executive")
  )

def https_row_for(domain):
  inspect = domain_data[domain]['inspect']
  row = {
    "Domain": domain,
    "Canonical": inspect["Canonical"],
    "Agency": domain_data[domain]['agency']
  }

  ###
  # Is it there? There for most clients? Not there?

  # assumes that HTTPS would be technically present, with or without issues
  if (inspect["Downgrades HTTPS"] == "True"):
    https = 0 # No
  else:
    if (inspect["Valid HTTPS"] == "True"):
      https = 2 # Yes
    elif (inspect["HTTPS Bad Chain"] == "True"):
      https = 1 # Yes
    else:
      https = -1 # No

  row[LABELS['https']] = https;


  ###
  # Is HTTPS enforced?

  if (https <= 0):
    behavior = 0 # N/A

  else:

    # "Yes (Strict)" means HTTP immediately redirects to HTTPS,
    # *and* that HTTP eventually redirects to HTTPS.
    #
    # Since a pure redirector domain can't "default" to HTTPS
    # for itself, we'll say it "Enforces HTTPS" if it immediately
    # redirects to an HTTPS URL.
    if (
      (inspect["Strictly Forces HTTPS"] == "True") and
      (
        (inspect["Defaults to HTTPS"] == "True") or
        (inspect["Redirect"] == "True")
      )
    ):
      behavior = 3 # Yes (Strict)

    # "Yes" means HTTP eventually redirects to HTTPS.
    elif (
      (inspect["Strictly Forces HTTPS"] == "False") and
      (inspect["Defaults to HTTPS"] == "True")
    ):
      behavior = 2 # Yes

    # Either both are False, or just 'Strict Force' is True,
    # which doesn't matter on its own.
    # A "present" is better than a downgrade.
    else:
      behavior = 1 # Present (considered 'No')

  row[LABELS['https_forced']] = behavior;


  ###
  # Characterize the presence and completeness of HSTS.

  if inspect["HSTS Max Age"]:
    hsts_age = int(inspect["HSTS Max Age"])
  else:
    hsts_age = None

  # Without HTTPS there can be no HSTS.
  if (https <= 0):
    hsts = -1 # N/A (considered 'No')

  else:

    # HTTPS is there, but no HSTS header.
    if (inspect["HSTS"] == "False"):
      hsts = 0 # No

    # HSTS preload ready already implies a minimum max-age, and
    # may be fine on the root even if the canonical www is weak.
    elif (inspect["HSTS Preload Ready"] == "True"):
      hsts = 3 # Yes

    # We'll make a judgment call here.
    #
    # The OMB policy wants a 1 year max-age (31536000).
    # The HSTS preload list wants an 18 week max-age (10886400).
    #
    # We don't want to punish preload-ready domains that are between
    # the two.
    #
    # So if you're below 18 weeks, that's a No.
    # If you're between 18 weeks and 1 year, it's a Yes
    # (but you'll get a warning in the extended text).
    # 1 year and up is a yes.
    elif (hsts_age < 10886400):
      hsts = 0 # No, too weak

    else:
      # This kind of "Partial" means `includeSubdomains`, but no `preload`.
      if (inspect["HSTS All Subdomains"] == "True"):
        hsts = 2 # Yes

      # This kind of "Partial" means HSTS, but not on subdomains.
      else: # if (inspect["HSTS"] == "True"):

        hsts = 1 # Yes

  row[LABELS['hsts']] = hsts
  row[LABELS['hsts_age']] = hsts_age


  ###
  # Include the SSL Labs grade for a domain.

  tls = domain_data[domain].get('tls')

  fs = None
  sig = None
  ssl3 = None
  tls12 = None
  rc4 = None

  # Not relevant if no HTTPS
  if (https <= 0):
    grade = -1 # N/A

  elif tls is None:
    # print("[https][%s] No TLS scan data found." % domain)
    grade = -1 # N/A

  else:

    grade = {
      "F": 0,
      "T": 1,
      "C": 2,
      "B": 3,
      "A-": 4,
      "A": 5,
      "A+": 6
    }[tls["Grade"]]

    ###
    # Construct a sentence about the domain's TLS config.
    #
    # Consider SHA-1, FS, SSLv3, and TLSv1.2 data.

    fs = int(tls["Forward Secrecy"])
    sig = tls["Signature Algorithm"]
    rc4 = boolean_for(tls["RC4"])
    ssl3 = boolean_for(tls["SSLv3"])
    tls12 = boolean_for(tls["TLSv1.2"])

  row[LABELS['grade']] = grade
  row[LABELS['fs']] = fs
  row[LABELS['sig']] = sig
  row[LABELS['rc4']] = rc4
  row[LABELS['ssl3']] = ssl3
  row[LABELS['tls12']] = tls12

  return row

# Given the data we have about a domain, what's the DAP row?
def analytics_row_for(domain):
  analytics = domain_data[domain]['analytics']
  inspect = domain_data[domain]['inspect']

  row = {
    "Domain": domain,
    "Canonical": inspect["Canonical"],
    "Agency": domain_data[domain]['agency']
  }

  # rename column in process
  row[LABELS['dap']] = boolean_nice(analytics['Participates in Analytics'])

  return row

# Make a tiny CSV about each stat, to be downloaded for D3 rendering.
def process_stats():
  global https_stats, analytics_stats

  total = len(https_domains)
  enabled = 0
  for row in https_domains:
    # HTTPS needs to be enabled.
    # It's okay if it has a bad chain.
    # However, it's not okay if HTTPS is downgraded.
    if (
      (row[LABELS['https']] >= 1) and
      (row[LABELS['https_forced']] >= 1)
    ):
      enabled += 1

  pct = percent(enabled, total)

  https_stats = [
    ['status', 'value'],
    ['active', pct],
    ['inactive', 100-pct]
  ]

  total = len(analytics_domains)
  enabled = 0
  for row in analytics_domains:
    # Enabled ('Yes')
    if row[LABELS['dap']] >= 1:
      enabled += 1
  pct = percent(enabled, total)

  analytics_stats = [
    ['status', 'value'],
    ['active', pct],
    ['inactive', 100-pct]
  ]


def percent(num, denom):
  return round((num / denom) * 100)

def boolean_nice(value):
  if value == "True":
    return 1
  elif value == "False":
    return 0
  else:
    return -1

# Given the rows we've made, save them to disk.
def save_tables():
  https_path = os.path.join(TABLE_DATA, "https/domains.json")
  https_data = json_for({'data': https_domains})
  write(https_data, https_path)

  https_agencies_path = os.path.join(TABLE_DATA, "https/agencies.json")
  https_agencies_data = json_for({'data': https_agencies})
  write(https_agencies_data, https_agencies_path)

  analytics_path = os.path.join(TABLE_DATA, "analytics/domains.json")
  analytics_data = json_for({'data': analytics_domains})
  write(analytics_data, analytics_path)

  analytics_agencies_path = os.path.join(TABLE_DATA, "analytics/agencies.json")
  analytics_agencies_data = json_for({'data': analytics_agencies})
  write(analytics_agencies_data, analytics_agencies_path)

# Given the rows we've made, save some top-level #'s to disk.
def save_stats():
  f = open(os.path.join(STATS_DATA, "https.csv"), 'w', newline='')
  writer = csv.writer(f)
  for row in https_stats:
    writer.writerow(row)
  f.close()

  f = open(os.path.join(STATS_DATA, "analytics.csv"), 'w', newline='')
  writer = csv.writer(f)
  for row in analytics_stats:
    writer.writerow(row)
  f.close()



### utilities

def boolean_for(string):
  if string == "False":
    return False
  else:
    return True

def json_for(object):
  return json.dumps(object, sort_keys=True,
                    indent=2, default=format_datetime)

def format_datetime(obj):
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    elif isinstance(obj, str):
        return obj
    else:
        return None


def branch_for(agency):
  if agency in [
    "Library of Congress",
    "The Legislative Branch (Congress)",
    "Government Printing Office",
    "Congressional Office of Compliance"
  ]:
    return "legislative"

  if agency in ["The Judicial Branch (Courts)"]:
    return "judicial"

  if agency in ["Non-Federal Agency"]:
    return "non-federal"

  else:
    return "executive"

def write(content, destination):
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    f = open(destination, 'w', encoding='utf-8')
    f.write(content)
    f.close()

### Run when executed.

if __name__ == '__main__':
    run()
