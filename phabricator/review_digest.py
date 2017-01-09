from collections import defaultdict
from datetime import datetime, timedelta
from email.mime.text import MIMEText
import smtplib

from jinja2 import Template
from phabricator import Phabricator


ALIASES = [
    'barykin',
    'victor',
    'kuan',
    'farshid',
    'mallik',
    'jack',
    'tamara',
    'jasmine',
    'geoffrey',
    'patrick',
    'jacques',
    'elliot',
    'romulo'
]

MAX_DAYS = 7
MAX_DIFFS = 5

USER = ''
PASS = ''
EMAIL = ''

EMAIL_TEMPLATE = '''
{% macro format_review(review) %}
    <a href="{{ review.uri }}">D{{ review.id }}</a> | {{ review.dateString }} |
    {{ review.diffs|length }} diffs | {{ review.title }}
{% endmacro %}
{% macro list_reviews(reviews, category) %}
    {% if reviews[category] %}
        <div>{{ category }}</div>
        <ul>
        {% for review in reviews[category] %}
            <li>{{ format_review(review) }}</li>
        {% endfor %}
        </ul>
    {% endif %}
{% endmacro %}
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN">
<html lang="en">
<body>
    {% for user, reviews in users_to_reviews.iteritems() %}
        <h4>{{ user|lower }}</h4>
        {% if reviews['new_reviews'] %}
            <div>New Reviews</div>
            <ul>
            {% for review in reviews.new_reviews %}
                <li>{{ format_review(review) }}</li>
            {% endfor %}
            </ul>
        {% endif %}
        {% if reviews['long_reviews'] %}
            <div>Long Reviews</div>
            <ul>
            {% for review in reviews.long_reviews %}
                <li>{{ format_review(review) }}</li>
            {% endfor %}
            </ul>
        {% endif %}
    {% endfor %}
</body>
</html>
'''


def find_user_ids(phab):
    users = phab.user.find(aliases=ALIASES)
    return users.response


def find_reviews_for_user(phab, user_id):
    reviews = phab.differential.query(authors=[user_id])
    sorted_reviews = defaultdict(list)
    cutoff_date = datetime.now() - timedelta(days=MAX_DAYS)
    for review in reviews:
        date_created = datetime.fromtimestamp(float(review['dateCreated']))
        if date_created > cutoff_date:
            sorted_reviews['new_reviews'].append(review)
            review['dateString'] = date_created.strftime('%Y-%m-%d')
        if (len(review['diffs']) > MAX_DIFFS or date_created < cutoff_date) \
        and review['statusName'] not in ['Closed', 'Abandoned']:
            review['dateString'] = date_created.strftime('%Y-%m-%d')
            sorted_reviews['long_reviews'].append(review)
    return sorted_reviews


def find_reviews(phab, aliases_to_user_ids):
    reviews = {}
    for alias, user_id in aliases_to_user_ids.iteritems():
        print 'Finding reviews for {}'.format(alias)
        reviews[alias] = find_reviews_for_user(phab, user_id)
    return reviews


def email_report(users_to_reviews):
    template = Template(EMAIL_TEMPLATE)
    message_text = template.render(users_to_reviews=users_to_reviews)
    message = MIMEText(message_text, 'html')
    message['Subject'] = 'Phabricator Digest'
    message['From'] = EMAIL
    message['To'] = EMAIL

    s = smtplib.SMTP('smtp.sendgrid.net', 587)
    s.login(USER, PASS)
    s.sendmail(EMAIL, EMAIL, message.as_string())
    s.quit()


def main():
    phab = Phabricator()
    aliases_to_user_ids = find_user_ids(phab)
    users_to_reviews = find_reviews(phab, aliases_to_user_ids)
    email_report(users_to_reviews)


if __name__ == "__main__":
    main()
