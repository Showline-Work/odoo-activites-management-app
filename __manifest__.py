{
    "name": "Activities Management",
    "version": "19.0.1.0.0",
    "summary": "Google Tasks-like activity management",
    "description": """Activities Management - Production Ready""",
    "category": "Productivity",
    "author": "Havano",
    "license": "LGPL-3",
    "depends": ["base", "mail", "web"],
    "data": [
        "security/ir.model.access.csv",
        "views/activity_views.xml",
        "views/activity_menus.xml",
        "data/activity_cron.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "/activities_management/static/src/js/activity_recurrence_dialog.js",
            "/activities_management/static/src/xml/recurrence_dialog.xml",
            "/activities_management/static/src/scss/activity.scss",
        ],
    },
    "application": True,
    "installable": True,
}