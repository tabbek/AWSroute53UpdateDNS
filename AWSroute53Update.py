"""
 Requeriments:
     boto dnspython
"""
import time
import sys
import urllib2
import dns.resolver
from boto.route53.connection import Route53Connection
from boto.route53.exception import DNSServerError
from boto.route53.record import ResourceRecordSets
import logging

# Settings, Change me!
HOSTED_ZONE = ''
DOMAIN_NAME = ''
aws_access_key_id=''
aws_secret_access_key=''

class AWSroute53Update:
    """
    AWSroute53Update
    Updates the A record for a DNS entry in AWS Route53

    zoneid - The Route53 unique hosted zone id
    domainname - The domain name being checked / updated
    awskey - The account aws_access_key_id
    awssecret - the account aws_secret_access_key

    Example:
        updater = AWSroute53Update('ABCDEFGHI', 'example.domain.com', 'SADIFHASDJFLKASOLDFJ', 'ASDFASDFASDF')
    """
    def __init__(self, zoneid, domainname, awskey, awssecret):
        self.logger = self.setup_logger()
        self.zoneid = zoneid
        self.domainname = domainname
        self.awskey = awskey
        self.awssecret = awssecret
        self.get_change_id = lambda response: response['ChangeInfo']['Id'].split('/')[-1]
        self.get_change_status = lambda response: response['ChangeInfo']['Status']

    def setup_logger(self):
        logger = logging.getLogger(__name__)
        handler = logging.FileHandler('AWSroute53Update.log')
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        #logger.setLevel(logging.INFO)
        logger.setLevel(logging.DEBUG)
        return logger


    def resolve_name_ip(self, name):
        resolver = dns.resolver.Resolver()
        resolver.nameservers = [
            '8.8.8.8',
            '8.8.4.4'
        ]
        answer = resolver.query(name)
        return answer.response.answer[0].items[0].address


    def run(self):
        # Get your ip using a public service
        current_ip = urllib2.urlopen('http://ip.42.pl/raw').read()

        # Avoid to hit the Route53 API if is not necessary.
        # so compare first to a DNS server if the IP changed
        resolved_ip = self.resolve_name_ip(self.domainname)
        if resolved_ip == current_ip:
            self.logger.debug('DNS response (%s) and public IP (%s) are the same, nothing to do' % (resolved_ip, current_ip))
            return

        conn = Route53Connection(aws_access_key_id=self.awskey, aws_secret_access_key=self.awssecret)

        try:
            zone = conn.get_hosted_zone(self.zoneid)
        except DNSServerError:
            self.logger.error('%s Zone Not Found' % self.zoneid)
            sys.exit(1)

        response = conn.get_all_rrsets(self.zoneid, 'A', self.domainname, maxitems=1)[0]

        if current_ip not in response.resource_records:
            self.logger.info('Found new IP: %s' % current_ip)

            # Delete the old record, and create a new one.
            # This code is from route53.py script, the change record command
            changes = ResourceRecordSets(conn, self.zoneid, '')
            change1 = changes.add_change("DELETE", self.domainname, 'A', response.ttl)
            for old_value in response.resource_records:
                change1.add_value(old_value)
            change2 = changes.add_change("CREATE", self.domainname, 'A', response.ttl)
            change2.add_value(current_ip)

            try:
                commit = changes.commit()
                self.logger.debug('%s' % commit)
            except:
                self.logger.error("Changes can't be made: %s" % commit)
                sys.exit(1)
            else:

                change = conn.get_change(self.get_change_id(commit['ChangeResourceRecordSetsResponse']))
                self.logger.debug('%s' % change)

                while self.get_change_status(change['GetChangeResponse']) == 'PENDING':
                    time.sleep(2)
                    change = conn.get_change(self.get_change_id(change['GetChangeResponse']))
                    self.logger.debug('%s' % change)
                if self.get_change_status(change['GetChangeResponse']) == 'INSYNC':
                    self.logger.info('Change %s A de %s -> %s' % (self.domainname, response.resource_records[0], current_ip))
                else:
                    self.logger.warning('Unknown status for the change: %s' % change)
                    self.logger.debug('%s' % change)


if __name__ == '__main__':
    updater = AWSroute53Update(HOSTED_ZONE, DOMAIN_NAME, aws_access_key_id, aws_secret_access_key)
    updater.run()
