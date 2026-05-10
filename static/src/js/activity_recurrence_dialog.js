/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

console.log("✅ Activities Management Recurrence Dialog Loaded!");

class RecurrenceDialog extends Component {
  static template = "activities_management.RecurrenceDialog";

  setup() {
    this.orm = useService("orm");
    this.notification = useService("notification");
    this.activityId = this.props.activity_id;

    const now = new Date();
    const day = now.getDay();
    this.monDay = day === 0 ? 6 : day - 1;
    this.curDate = now.getDate();
    this.curMonth = now.getMonth() + 1;
    this.curFullDayName = [
      "Sunday",
      "Monday",
      "Tuesday",
      "Wednesday",
      "Thursday",
      "Friday",
      "Saturday",
    ][day];
    this.curMonthName = [
      "January",
      "February",
      "March",
      "April",
      "May",
      "June",
      "July",
      "August",
      "September",
      "October",
      "November",
      "December",
    ][now.getMonth()];

    this.state = useState({
      mode: "weekly",
      interval: 1,
      days: [this.monDay],
      dayOfMonth: this.curDate,
      month: this.curMonth,
      endType: "never",
      endDate: "",
      count: 10,
    });
  }

  get dayNames() {
    return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  }

  get fullDayNames() {
    return [
      "Monday",
      "Tuesday",
      "Wednesday",
      "Thursday",
      "Friday",
      "Saturday",
      "Sunday",
    ];
  }

  get monthNames() {
    return [
      "January",
      "February",
      "March",
      "April",
      "May",
      "June",
      "July",
      "August",
      "September",
      "October",
      "November",
      "December",
    ];
  }

  get modeLabel() {
    const labels = {
      daily: "days",
      weekly: "weeks",
      monthly: "months",
      yearly: "years",
      custom: "days",
    };
    return labels[this.state.mode] || "days";
  }

  get weeklyDayLabel() {
    if (this.state.days.length === 0) return "Weekly";
    if (this.state.days.length === 1)
      return `Weekly on ${this.fullDayNames[this.state.days[0]]}`;
    const names = this.state.days.map((d) => this.dayNames[d]).join(", ");
    return `Weekly on ${names}`;
  }

  get monthlyLabel() {
    const d = this.state.dayOfMonth || this.curDate;
    const suffix = d === 1 ? "st" : d === 2 ? "nd" : d === 3 ? "rd" : "th";
    return `Monthly on the ${d}${suffix}`;
  }

  get yearlyLabel() {
    const m = this.monthNames[this.state.month - 1] || this.curMonthName;
    const d = this.state.dayOfMonth || this.curDate;
    return `Annually on ${m} ${d}`;
  }

  get showDays() {
    return this.state.mode === "weekly";
  }
  get showDayOfMonth() {
    return ["monthly", "yearly", "custom"].includes(this.state.mode);
  }
  get showMonth() {
    return ["yearly", "custom"].includes(this.state.mode);
  }

  toggleDay(i) {
    if (this.state.days.includes(i)) {
      this.state.days = this.state.days.filter((d) => d !== i);
    } else {
      this.state.days = [...this.state.days, i].sort();
    }
  }

  isDaySelected(i) {
    return this.state.days.includes(i);
  }

  get selectedDaysList() {
    if (this.state.days.length === 0) return "";
    return this.state.days.map((d) => this.fullDayNames[d]).join(", ");
  }

  async save() {
    const updates = {
      is_recurring: this.state.mode !== "none",
      recurrence_mode: this.state.mode,
      recurrence_interval: this.state.interval,
      recurrence_day_of_month: this.state.dayOfMonth,
      recurrence_month: this.state.month,
      recurrence_end_type: this.state.endType,
    };
    if (this.state.mode === "weekly")
      updates.recurrence_days = this.state.days.join(",");
    if (this.state.endType === "date")
      updates.recurrence_end_date = this.state.endDate;
    if (this.state.endType === "count")
      updates.recurrence_count = this.state.count;

    try {
      await this.orm.write("activity.management", [this.activityId], updates);
      this.notification.add("✅ Recurrence saved!", { type: "success" });
      this.props.close();
      window.location.reload();
    } catch (e) {
      this.notification.add("Error saving recurrence", { type: "danger" });
    }
  }

  cancel() {
    this.props.close();
  }
  selectNone() {
    this.state.mode = "none";
  }
  selectDaily() {
    this.state.mode = "daily";
    this.state.interval = 1;
  }
  selectWeekly() {
    this.state.mode = "weekly";
    this.state.interval = 1;
    if (!this.state.days.length) this.state.days = [this.monDay];
  }
  selectMonthly() {
    this.state.mode = "monthly";
    this.state.interval = 1;
  }
  selectYearly() {
    this.state.mode = "yearly";
    this.state.interval = 1;
  }
  selectCustom() {
    this.state.mode = "custom";
    this.state.interval = 1;
  }
}

function recurrenceModalAction(env, action) {
  env.services.dialog.add(RecurrenceDialog, {
    activity_id: action.params.activity_id,
  });
  return { type: "ir.actions.act_window_close" };
}

registry
  .category("actions")
  .add("activities_management.recurrence_modal", recurrenceModalAction);
