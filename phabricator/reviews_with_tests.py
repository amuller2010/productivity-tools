#!/usr/bin/python
import optparse
import sys

from phabricator import Phabricator


def parse_args():
    usage = './%prog user1 [user2 ...]'
    parser = optparse.OptionParser(usage=usage)
    opts, args = parser.parse_args()
    if len(args) < 1:
        parser.print_help()
        sys.exit(0)
    return args


def find_user_ids(aliases, phab):
    users = phab.user.find(aliases=aliases)
    return users.response


def find_reviews_with_tests(usernames_to_user_ids, phab):
    for username, user_id in usernames_to_user_ids.iteritems():
        all_reviews = phab.differential.query(
            authors=[user_id],
            limit=100  # TODO: make limit configurable
        )
        reviews_with_tests = []
        for review in all_reviews:
            if contains_test_change(review, phab):
                reviews_with_tests.append(review)
        print '{0}: {1} out of {2} code reviews have a test change ({3:.0f}%)'.format(
            username,
            len(reviews_with_tests),
            len(all_reviews),
            percent(len(reviews_with_tests), len(all_reviews))
        )


def contains_test_change(review, phab):
    # The paths argument to the query api can find changes to
    # tests/ and integration_tests/ in one call. However, it cannot
    # detect our C++ tests which are distinguished by filename
    # rather than directory structure.
    #
    # Unfortunately this api only supports one review id at a time.
    # A batch endpoint would speed up the runtime of the script
    # considerably.
    commits = phab.differential.getcommitpaths(
        revision_id=int(review['id'])
    )
    for commit in commits:
        if 'test' in commit:
            return True
    return False


def percent(x, y):
    if y == 0:
        return 100
    return x / float(y) * 100


def main():
    usernames = parse_args()
    phab = Phabricator()
    usernames_to_user_ids = find_user_ids(usernames, phab)
    find_reviews_with_tests(usernames_to_user_ids, phab)


if __name__ == "__main__":
    main()
