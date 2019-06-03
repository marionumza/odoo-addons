import re
import pytz
from odoo import models, api, fields, _
from odoo.exceptions import UserError


class PartnerAnalysisWizard(models.TransientModel):
    _name = 'partner.analysis.wizard'
    _description = 'Partner Analysis Wizard'

    clear_previous = fields.Boolean(
        string='Clear previous selection', default=True,
        help="If flagged all previous selection will be removed.")
    result_order = fields.Selection([
        ('DESC', 'ASC'), ('ASC', 'DESC')], default='ASC')
    limit = fields.Integer('Limit in research')
    age_from = fields.Integer('From age')
    age_to = fields.Integer('To age')
    city = fields.Char('City')
    state_id = fields.Many2one('res.country.state', 'State')
    country_id = fields.Many2one('res.country', 'Country')
    sex = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
    ], string='Sex')

    select_dates = fields.Boolean(string='Select dates')
    date_from = fields.Datetime(string='Date from')
    date_to = fields.Datetime(string='Date to')

    select_hours = fields.Boolean('Select hours')
    from_hr = fields.Char(string='From:', help="Write hour in format HH:MM")
    to_hr = fields.Char(string='To:', help="Write hour in format HH:MM")

    def partner_analysis(self):
        partner_obj = self.env['res.partner']
        limit = "LIMIT {}".format(self.limit) if self.limit else ""

        # manage time errors and query
        local_timezone = pytz.timezone(self._context.get('tz'))
        if not local_timezone:
            raise UserError('Please set the time zone on the user!')
        date_from = self.date_from.replace(
            tzinfo=pytz.utc).astimezone(local_timezone)
        date_to = self.date_to.replace(
            tzinfo=pytz.utc).astimezone(local_timezone)

        time_re = re.compile(r'^(([01]\d|2[0-3]):([0-5]\d)|24:00)$')
        if self.select_hours:
            if not (bool(time_re.match(self.from_hr) and
                         bool(time_re.match(self.to_hr)))):
                raise UserError(
                    'Hours fields for filtering is not in the correct '
                    'format, which is HH:MM . Please check')
            hours_range = "AND '{}:00' <= time_detail " \
                "AND time_detail <= '{}:00'".format(self.from_hr, self.to_hr)
        else:
            hours_range = ""

        main_query = """
        SELECT partner_id, sum(amount) as amount, sum(points) as points
        FROM (
                    SELECT  partner_id, amount, points, date, 
                    CAST(date::timestamp::time AS time) AS time_detail
            FROM fidelity_transaction ft
            ) AS data
        WHERE date BETWEEN '{_01}' AND '{_02}'
        {_05}

        GROUP BY partner_id
        ORDER BY points {_03}
        {_04}
        """.format(_01=date_from,
                   _02=date_to,
                   _03=self.result_order,
                   _04=limit,
                   _05=hours_range,
                   )

        self.env.cr.execute(main_query)
        lines = self.env.cr.fetchall()

        client_ids = [x[0] for x in lines]
        # set to false the parameter on ALL partners
        if self.clear_previous:
            partners = partner_obj.search([
                ('fidelity_selection', '=', True)
            ])
            partners.update({'fidelity_selection': False})

        # managing optional parameters
        clients = partner_obj.browse(client_ids)

        if self.sex:
            clients = clients.filtered(lambda c: c.sex == self.sex)
        if self.age_to and self.age_from > self.age_to:
            raise UserError(_("'From age' can not be smaller than 'To age'."))
        if self.age_from:
            clients = clients.filtered(lambda c: c.age >= self.age_from)
        if self.age_to:
            clients = clients.filtered(lambda c: c.age <= self.age_to)
        if self.city:
            clients = clients.filtered(lambda c: c.city == self.city)
        if self.state_id:
            clients = clients.filtered(lambda c: c.state_id == self.state_id)
        if self.country_id:
            clients = clients.filtered(
                lambda c: c.country_id == self.country_id)

        # setting parameter on new partners
        clients.update({'fidelity_selection': True})

        return {
            "type": "ir.actions.do_nothing"
        }
