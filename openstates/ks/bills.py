import re
import os
import datetime
import json

from billy.scrape.bills import BillScraper, Bill
from billy.scrape.votes import Vote
from billy.scrape import NoDataForPeriod

import ksapi

votes_re = re.compile('(.*)[ ;]+Yea: ([0-9]+) Nay: ([0-9]+)$')

class KSBillScraper(BillScraper):
    state = 'ks'

    def scrape(self, chamber, term):
        self.validate_term(term, latest_only=True)
        self.scrape_current(chamber, term)

    def scrape_current(self, chamber, term):
        chamber_name = 'Senate' if chamber == 'upper' else 'House'
        chamber_letter = chamber_name[0]
        # perhaps we should save this data so we can make one request for both?
        with self.urlopen(ksapi.url + 'bill_status/') as bill_request:
            bill_request_json = json.loads(bill_request)
            bills = bill_request_json['content']
            for bill_data in bills:

                bill_id = bill_data['BILLNO']

                # filter other chambers
                if not bill_id.startswith(chamber_letter):
                    continue

                if 'CR' in bill_id:
                    btype = 'concurrent resolution'
                elif 'R' in bill_id:
                    btype = 'resolution'
                elif 'B' in bill_id:
                    btype = 'bill'

                # main
                bill = Bill(term, chamber, bill_id, bill_data['SHORTTITLE'],
                            type=btype, status=bill_data['STATUS'])
                bill.add_source(ksapi.url + 'bill_status/' +
                                bill_data['BILLNO'].lower())
                if bill_data['LONGTITLE']:
                    bill.add_title(bill_data['LONGTITLE'])
                bill.add_version('Latest', ksapi.ksleg + bill_data['apn'])

                for sponsor in bill_data['SPONSOR_NAMES']:
                    stype = ('primary' if len(bill_data['SPONSOR_NAMES']) == 1
                             else 'cosponsor')
                    bill.add_sponsor(stype, sponsor)

                # history is backwards
                for event in reversed(bill_data['HISTORY']):
                    append = ''
                    if 'committee_names' in event:
                        actor = ' and '.join(event['committee_names'])
                        append = actor
                    else:
                        actor = 'upper' if chamber == 'Senate' else 'lower'

                    date = datetime.datetime.strptime(event['occurred_datetime'], "%Y-%m-%dT%H:%M:%S")
                    # append committee name if present
                    action = event['status'] + append
                    if event['action_code'] not in ksapi.action_codes:
                        self.warning('unknown action code on %s: %s %s' %
                                     (bill_data['BILLNO'], event['action_code'],
                                     event['status']))
                        atype = 'other'
                    else:
                        atype = ksapi.action_codes[event['action_code']]
                    bill.add_action(actor, action, date, type=atype)

                    votes = votes_re.match(event['status'])
                    if votes:
                        vote = Vote(chamber, date, votes.group(1),
                                    event['action_code'] in ksapi.passed,
                                    int(votes.group(2)),
                                    int(votes.group(3)),
                                    0)
                        bill.add_vote(vote)

                self.save_bill(bill)