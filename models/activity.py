import calendar
import logging
from datetime import date, datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ActivityManagement(models.Model):
    _name = "activity.management"
    _description = "Activities Management"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "priority desc, date_start asc, id desc"
    _rec_name = "name"

    # ========== BASIC FIELDS ==========
    name = fields.Char(string="Title", required=True, tracking=True)
    description = fields.Html(string="Description")
    note = fields.Text(string="Note", tracking=True)

    # ========== PEOPLE ==========
    user_ids = fields.Many2many(
        "res.users", "activity_management_user_rel",
        "activity_id", "user_id",
        string="Assigned To", tracking=True,
    )
    collaborator_ids = fields.Many2many(
        "res.users", "activity_management_collaborator_rel",
        "activity_id", "user_id",
        string="Collaborators", tracking=True,
    )
    customer_id = fields.Many2one(
        "res.partner", string="Customer", tracking=True,
        domain="[('customer_rank', '>', 0)]",
    )

    # ========== TYPE & PRIORITY ==========
    activity_type_id = fields.Many2one(
        "mail.activity.type", string="Activity Type",
        tracking=True, ondelete="set null",
    )
    priority = fields.Selection(
        [("0", "None"), ("1", "Low"), ("2", "Medium"), ("3", "High"), ("4", "Urgent")],
        string="Priority", default="2", tracking=True,
    )

    # ========== DATES ==========
    date_start = fields.Datetime(
        string="Start Date", tracking=True,
        default=lambda self: fields.Datetime.now(),
    )
    date_due = fields.Datetime(string="Due Date", tracking=True)
    date_done = fields.Datetime(string="Completion Date", tracking=True, readonly=True)
    duration_display = fields.Char(
        string="Duration", compute="_compute_duration_display",
    )
    is_all_day = fields.Boolean(string="All Day", tracking=True)

    # ========== STATUS ==========
    state = fields.Selection(
        [("new", "Not Started"), ("in_progress", "In Progress"),
         ("done", "Done"), ("cancelled", "Cancelled")],
        string="Status", default="new", required=True, tracking=True,
    )

    # ========== RECURRING ==========
    is_recurring = fields.Boolean(string="Repeat", tracking=True)
    recurrence_mode = fields.Selection(
        [("none", "Does not repeat"), ("daily", "Daily"),
         ("weekly", "Weekly"), ("monthly", "Monthly"),
         ("yearly", "Yearly"), ("custom", "Custom")],
        string="Recurrence Mode", default="none", tracking=True,
    )
    recurrence_interval = fields.Integer(string="Repeat Every", default=1, tracking=True)
    recurrence_days = fields.Char(
        string="On Days",
        help="Comma-separated: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun",
        tracking=True
    )
    recurrence_day_of_month = fields.Integer(string="Day of Month", tracking=True)
    recurrence_month = fields.Integer(string="Month", tracking=True)
    recurrence_end_type = fields.Selection(
        [("never", "Never"), ("date", "On Date"), ("count", "After Occurrences")],
        string="End Type", default="never", tracking=True,
    )
    recurrence_end_date = fields.Date(string="End Date", tracking=True)
    recurrence_count = fields.Integer(string="Max Occurrences", tracking=True)

    # ========== HIERARCHY ==========
    parent_id = fields.Many2one(
        "activity.management", string="Parent Activity",
        ondelete="cascade", index=True,
    )
    child_ids = fields.One2many(
        "activity.management", "parent_id", string="Sub-Activities",
    )

    # ========== DOCUMENT LINKING ==========
    res_model = fields.Char(string="Related Model", tracking=True)
    res_id = fields.Integer(string="Related ID", tracking=True)
    res_name = fields.Char(string="Related Name", compute="_compute_res_name", store=True)

    # ========== COMPANY ==========
    company_id = fields.Many2one(
        "res.company", string="Company",
        default=lambda self: self.env.company,
    )

    # ========== COMPUTED FIELDS ==========
    is_overdue = fields.Boolean(string="Overdue", compute="_compute_is_overdue", store=True)
    sub_activity_count = fields.Integer(
        string="Sub-Activities", compute="_compute_sub_activity_count",
    )
    recurrence_display = fields.Char(
        string="Recurrence Display", compute="_compute_recurrence_display",
    )

    # ========== RECURRENCE MAX INSTANCES ==========
    MAX_RECURRING_INSTANCES = 100  # Max instances to create per batch

    def open_recurrence_modal(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'activities_management.recurrence_modal',
            'params': {'activity_id': self.id},
            'target': 'new',
        }

    # ========== CRON JOB ==========
    @api.model
    def _cron_generate_recurring_occurrences(self):
        """Generate upcoming occurrences in batches to avoid recursion."""
        today = fields.Date.context_today(self)
        look_ahead = today + timedelta(days=30)

        recurring_activities = self.search([
            ('is_recurring', '=', True),
            ('recurrence_mode', '!=', 'none'),
            ('state', 'not in', ('done', 'cancelled')),
        ])

        _logger.info("Checking %s recurring activities", len(recurring_activities))

        created_count = 0
        for activity in recurring_activities:
            # Count existing future occurrences
            existing_count = self.search_count([
                ('name', '=', activity.name),
                ('date_start', '>', activity.date_start),
                ('date_start', '>=', today),
            ])

            # Only create if under the max limit
            if existing_count < self.MAX_RECURRING_INSTANCES:
                existing_future = self.search([
                    ('name', '=', activity.name),
                    ('date_start', '>', activity.date_start),
                    ('date_start', '>=', today),
                    ('date_start', '<=', look_ahead),
                ], limit=1)

                if not existing_future:
                    next_date = activity._calculate_next_date()
                    if next_date and next_date <= look_ahead:
                        try:
                            activity._create_next_occurrence()
                            created_count += 1
                        except Exception as e:
                            _logger.error("Failed for activity #%s: %s", activity.id, str(e))

        _logger.info("Created %s upcoming occurrences", created_count)
        return True

    @api.model
    def _cron_cleanup_overdue_activities(self):
        """Cancel overdue recurring instances that are past due date without being completed."""
        today = fields.Datetime.now()
        overdue = self.search([
            ('state', '=', 'new'),
            ('date_due', '!=', False),
            ('date_due', '<', today),
            ('is_recurring', '=', True),
        ])
        overdue.write({'state': 'cancelled'})
        _logger.info("Cancelled %s overdue recurring activities", len(overdue))

    # ========== COMPUTE METHODS ==========
    @api.depends("date_start", "date_due", "is_all_day", "is_recurring", "recurrence_mode")
    def _compute_duration_display(self):
        for rec in self:
            if rec.is_recurring and rec.recurrence_mode == "daily":
                rec.duration_display = "Daily"
            elif rec.is_recurring and rec.recurrence_mode == "weekly":
                rec.duration_display = "Weekly"
            elif rec.is_recurring and rec.recurrence_mode == "monthly":
                rec.duration_display = "Monthly"
            elif rec.is_recurring and rec.recurrence_mode == "yearly":
                rec.duration_display = "Yearly"
            elif rec.date_start and rec.date_due:
                delta = rec.date_due - rec.date_start
                total_seconds = delta.total_seconds()
                if total_seconds < 3600:
                    minutes = int(total_seconds / 60)
                    rec.duration_display = f"{minutes}m"
                elif total_seconds < 86400:
                    hours = int(total_seconds / 3600)
                    rec.duration_display = f"{hours}h"
                else:
                    days = int(total_seconds / 86400)
                    rec.duration_display = f"{days}d"
            elif rec.date_start and not rec.date_due:
                rec.duration_display = "Indefinite"
            else:
                rec.duration_display = ""

    @api.depends("child_ids")
    def _compute_sub_activity_count(self):
        for rec in self:
            rec.sub_activity_count = len(rec.child_ids)

    @api.depends("res_model", "res_id")
    def _compute_res_name(self):
        for rec in self:
            rec.res_name = False
            if rec.res_model and rec.res_id:
                try:
                    target = self.env[rec.res_model].browse(rec.res_id)
                    rec.res_name = target.display_name if target.exists() else False
                except Exception:
                    rec.res_name = False

    @api.depends("date_due", "state")
    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for rec in self:
            rec.is_overdue = bool(
                rec.date_due and rec.date_due < now
                and rec.state not in ("done", "cancelled")
            )

    @api.depends("recurrence_mode", "recurrence_interval", "recurrence_days",
                  "recurrence_day_of_month", "recurrence_month")
    def _compute_recurrence_display(self):
        for rec in self:
            if not rec.is_recurring or rec.recurrence_mode == "none":
                rec.recurrence_display = "Does not repeat"
            elif rec.recurrence_mode == "daily":
                interval = rec.recurrence_interval or 1
                rec.recurrence_display = "Daily" if interval == 1 else f"Every {interval} days"
            elif rec.recurrence_mode == "weekly":
                days = rec._parse_weekdays()
                day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                if days:
                    day_str = ", ".join(day_names[d] for d in days)
                    rec.recurrence_display = f"Weekly on {day_str}"
                else:
                    rec.recurrence_display = "Weekly"
            elif rec.recurrence_mode == "monthly":
                day = rec.recurrence_day_of_month or (rec.date_start.day if rec.date_start else 1)
                rec.recurrence_display = f"Monthly on day {day}"
            elif rec.recurrence_mode == "yearly":
                month = rec.recurrence_month or (rec.date_start.month if rec.date_start else 1)
                day = rec.recurrence_day_of_month or (rec.date_start.day if rec.date_start else 1)
                month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                rec.recurrence_display = f"Annually on {month_names[month]} {day}"
            elif rec.recurrence_mode == "custom":
                rec.recurrence_display = "Custom"
            else:
                rec.recurrence_display = ""

    # ========== CONSTRAINTS ==========
    @api.constrains("date_start", "date_due")
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_due and rec.date_due < rec.date_start:
                raise ValidationError(_("Due date cannot be earlier than start date."))

    # ========== CRUD ==========
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("user_ids"):
                vals.setdefault("user_ids", [(4, self.env.user.id)])
            if vals.get("is_recurring") and vals.get("recurrence_mode") == "none":
                vals["recurrence_mode"] = "daily"
            if vals.get("is_recurring"):
                start = vals.get("date_start")
                if isinstance(start, str):
                    start = fields.Datetime.from_string(start)
                if start:
                    if not vals.get("recurrence_day_of_month"):
                        vals["recurrence_day_of_month"] = start.day
                    if not vals.get("recurrence_month"):
                        vals["recurrence_month"] = start.month
            
            # Sub-activity: inherit parent dates if not set
            if vals.get("parent_id") and not vals.get("date_start"):
                parent_id = vals["parent_id"]
                if isinstance(parent_id, int):
                    parent = self.browse(parent_id)
                    if parent.exists() and parent.date_start:
                        vals["date_start"] = parent.date_start
            if vals.get("parent_id") and not vals.get("date_due"):
                parent_id = vals["parent_id"]
                if isinstance(parent_id, int):
                    parent = self.browse(parent_id)
                    if parent.exists() and parent.date_due:
                        vals["date_due"] = parent.date_due
        
        records = super().create(vals_list)
        for rec in records:
            rec._notify_assignees(_("You have been assigned to '%s'.") % rec.name)

            if rec.is_recurring and rec.recurrence_mode != "none":
                try:
                    rec._create_next_occurrence()
                except Exception as e:
                    _logger.error("Failed to create next occurrence for #%s: %s", rec.id, str(e))

        return records

    def write(self, vals):
        if vals.get("is_recurring"):
            start = vals.get("date_start") or (self.date_start if self else None)
            if isinstance(start, str):
                start = fields.Datetime.from_string(start)
            if start:
                if not vals.get("recurrence_day_of_month"):
                    vals["recurrence_day_of_month"] = start.day
                if not vals.get("recurrence_month"):
                    vals["recurrence_month"] = start.month
        res = super().write(vals)
        if vals.get("state") == "done":
            for rec in self:
                if not rec.date_done:
                    rec.date_done = fields.Datetime.now()

        if vals.get("is_recurring") or vals.get("recurrence_mode") or vals.get("recurrence_interval"):
            for rec in self:
                if rec.is_recurring and rec.recurrence_mode != "none":
                    today = fields.Date.context_today(rec)
                    existing = self.search([
                        ('name', '=', rec.name),
                        ('date_start', '>', rec.date_start),
                        ('date_start', '>=', today),
                    ], limit=1)
                    if not existing:
                        try:
                            rec._create_next_occurrence()
                        except Exception as e:
                            _logger.error("Failed for #%s: %s", rec.id, str(e))

        return res

    # ========== ACTIONS ==========
    def action_start(self):
        self.filtered(lambda r: r.state == "new").write({"state": "in_progress"})

    def action_done(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.state in ("done", "cancelled"):
                continue
            rec.state = "done"
            rec.date_done = now
            rec.message_post(body=_("✅ Activity marked as done by %s") % self.env.user.display_name)
            if rec.is_recurring:
                rec._create_next_occurrence()

    def action_cancel(self):
        for rec in self:
            if rec.state == "done":
                continue
            rec.state = "cancelled"
            rec.message_post(body=_("❌ Activity cancelled by %s") % self.env.user.display_name)

    def action_reopen(self):
        for rec in self:
            if rec.state in ("done", "cancelled"):
                rec.state = "new"
                rec.date_done = False
                rec.message_post(body=_("🔄 Activity reopened by %s") % self.env.user.display_name)

    # ========== RECURRING LOGIC ==========
    def _parse_weekdays(self):
        self.ensure_one()
        if not self.recurrence_days:
            return []
        days = []
        for item in str(self.recurrence_days).split(","):
            item = item.strip()
            if item.isdigit():
                val = int(item)
                if 0 <= val <= 6:
                    days.append(val)
        return sorted(set(days)) if days else []

    def _calculate_next_date(self):
        self.ensure_one()
        base_date = self.date_start or fields.Datetime.now()
        if isinstance(base_date, str):
            base_date = fields.Datetime.from_string(base_date)
        base_date = base_date.date() if hasattr(base_date, 'date') else base_date

        today = fields.Date.context_today(self)
        if base_date < today:
            base_date = today

        interval = max(1, self.recurrence_interval or 1)

        if self.recurrence_mode == "daily":
            next_date = base_date + timedelta(days=interval)
        elif self.recurrence_mode == "weekly":
            weekdays = self._parse_weekdays() or [base_date.weekday()]
            candidate = base_date + timedelta(days=1)
            found = False
            for _ in range(366):
                if candidate.weekday() in weekdays:
                    if ((candidate - base_date).days // 7 or 1) % interval == 0:
                        next_date = candidate
                        found = True
                        break
                candidate += timedelta(days=1)
            if not found:
                next_date = base_date + timedelta(days=7 * interval)
        elif self.recurrence_mode == "monthly":
            day = self.recurrence_day_of_month or base_date.day
            month = base_date.month + interval
            year = base_date.year
            while month > 12:
                month -= 12
                year += 1
            last_day = calendar.monthrange(year, month)[1]
            next_date = date(year, month, min(day, last_day))
        elif self.recurrence_mode == "yearly":
            month = self.recurrence_month or base_date.month
            day = self.recurrence_day_of_month or base_date.day
            year = base_date.year + interval
            last_day = calendar.monthrange(year, month)[1]
            next_date = date(year, month, min(day, last_day))
        else:
            next_date = base_date + timedelta(days=1)

        if self.recurrence_end_type == "date" and self.recurrence_end_date:
            if next_date > self.recurrence_end_date:
                return None

        return next_date

    def _create_next_occurrence(self):
        self.ensure_one()
        if not self.is_recurring or self.recurrence_mode == "none":
            return False

        next_date = self._calculate_next_date()
        if not next_date:
            return False

        original_start = self.date_start
        if original_start and hasattr(original_start, 'hour'):
            next_start = datetime.combine(
                next_date,
                datetime.min.time().replace(hour=original_start.hour, minute=original_start.minute)
            )
        else:
            next_start = datetime.combine(next_date, datetime.min.time())

        if self.date_due and self.date_start:
            duration = self.date_due - self.date_start
            next_due = next_start + duration
        elif self.date_due:
            if hasattr(self.date_due, 'hour'):
                next_due = datetime.combine(next_date, self.date_due.time())
            else:
                next_due = datetime.combine(next_date, datetime.max.time().replace(hour=23, minute=59, second=59))
        else:
            next_due = datetime.combine(next_date, datetime.max.time().replace(hour=23, minute=59, second=59))

        vals = {
            "name": self.name,
            "description": self.description,
            "user_ids": [(6, 0, self.user_ids.ids)],
            "collaborator_ids": [(6, 0, self.collaborator_ids.ids)],
            "activity_type_id": self.activity_type_id.id,
            "priority": self.priority,
            "date_start": next_start,
            "date_due": next_due,
            "is_recurring": self.is_recurring,
            "recurrence_mode": self.recurrence_mode,
            "recurrence_interval": self.recurrence_interval,
            "recurrence_days": self.recurrence_days,
            "recurrence_day_of_month": self.recurrence_day_of_month,
            "recurrence_month": self.recurrence_month,
            "recurrence_end_type": self.recurrence_end_type,
            "recurrence_end_date": self.recurrence_end_date,
            "recurrence_count": self.recurrence_count - 1 if self.recurrence_end_type == "count" and self.recurrence_count and self.recurrence_count > 1 else self.recurrence_count,
            "parent_id": self.parent_id.id if self.parent_id else False,
            "res_model": self.res_model,
            "res_id": self.res_id,
            "customer_id": self.customer_id.id,
            "company_id": self.company_id.id,
        }
        next_activity = self.env["activity.management"].create(vals)
        next_activity.message_post(
            body=_("🔄 Recurring activity created from '%s'.") % self.name,
            message_type="notification",
        )
        return next_activity

    # ========== NOTIFICATIONS ==========
    def _notify_assignees(self, message):
        partners = (self.user_ids | self.collaborator_ids).mapped("partner_id")
        if partners:
            self.message_subscribe(partner_ids=partners.ids)
            self.message_post(body=message, partner_ids=partners.ids, message_type="notification")