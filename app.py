#!/usr/bin/env python3
"""
LEEH Exchange Admin Dashboard - Flask Web Backend
Real-time transaction monitoring and giveaway management
"""

import os
import csv
import uuid
import pandas as pd
import requests
import json
import re
from datetime import datetime
from flask import Flask, render_template, jsonify, request, session, redirect, flash, url_for
from flask_cors import CORS
from functools import wraps

# ─── Role definitions ───────────────────────────────────────────────────────
ROLES = {
    'transaction_manager': {
        'label': 'Transaction Manager',
        'icon': '💳',
        'description': 'Approve, reject and manage all buy/sell transactions',
        'color': '#007AFF',
        'permissions': ['transactions'],
    },
    'support_agent': {
        'label': 'Support Agent',
        'icon': '🎧',
        'description': 'View transactions and user profiles — read-only, no approval access',
        'color': '#34C759',
        'permissions': ['transactions_view', 'users'],
    },
    'email_manager': {
        'label': 'Email Manager',
        'icon': '📧',
        'description': 'Send email blasts, manage subscribers and review the email log',
        'color': '#FF9500',
        'permissions': ['emails'],
    },
    'giveaway_manager': {
        'label': 'Giveaway Manager',
        'icon': '🎁',
        'description': 'Verify and manage all giveaway claims and codes',
        'color': '#AF52DE',
        'permissions': ['giveaway'],
    },
    'content_manager': {
        'label': 'Content Manager',
        'icon': '📢',
        'description': 'Send broadcast messages and announcements to bot users',
        'color': '#FF3B30',
        'permissions': ['broadcast'],
    },
    'analyst': {
        'label': 'Analyst',
        'icon': '📊',
        'description': 'Read-only access to all data — stats, transactions, users and rates',
        'color': '#5AC8FA',
        'permissions': ['transactions_view', 'users', 'rates', 'giveaway_view'],
    },
    'moderator': {
        'label': 'Moderator',
        'icon': '🛡️',
        'description': 'Full operations access — manages transactions, giveaways and users',
        'color': '#8E44AD',
        'permissions': ['transactions', 'giveaway', 'users'],
    },
    'full_access': {
        'label': 'Full Access',
        'icon': '🔓',
        'description': 'Complete access to all sections — same as super admin except Settings',
        'color': '#FF6B00',
        'permissions': [
            'transactions', 'transactions_view', 'giveaway',
            'giveaway_view', 'broadcast', 'emails', 'users', 'rates',
        ],
    },
}

# All possible grantable permissions with labels (for the invite UI)
ALL_PERMISSIONS = [
    ('dashboard',         '🏠', 'Dashboard',          'Overview stats & summary cards'),
    ('transactions',      '💳', 'Transactions',        'Approve, reject & manage orders'),
    ('transactions_view', '👁️', 'Transactions (view)', 'View orders — read-only'),
    ('giveaway',          '🎁', 'Giveaway',            'Manage & verify giveaway claims'),
    ('giveaway_view',     '👁️', 'Giveaway (view)',     'View giveaway claims — read-only'),
    ('broadcast',         '📢', 'Broadcast',           'Send messages to all bot users'),
    ('emails',            '📧', 'Emails',              'Send bulk emails & manage subscribers'),
    ('users',             '👥', 'Users',               'View bot user profiles & activity'),
    ('rates',             '📊', 'Crypto Rates',        'View live cryptocurrency rates'),
]

# All permissions a super admin has
SUPER_ADMIN_PERMISSIONS = [
    'dashboard', 'transactions', 'transactions_view', 'giveaway', 'giveaway_view',
    'broadcast', 'emails', 'users', 'rates', 'settings', 'admins',
]

app = Flask(__name__)
app.secret_key = (os.getenv('SECRET_KEY') or os.getenv("SESSION_SECRET"))
CORS(app)

# Load admin config from file or environment
ADMIN_CONFIG_FILE = 'admin_config.json'

def load_admin_config():
    if os.path.exists(ADMIN_CONFIG_FILE):
        try:
            with open(ADMIN_CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading admin config: {e}")
    
    return {
        "admin_email": os.getenv('ADMIN_EMAIL'),
        "admin_id": os.getenv('ADMIN_ID'),
        "admin_password": os.getenv('ADMIN_PASSWORD'),
        "sender_email": "leehexchange@gmail.com"
    }

def save_admin_config(config):
    try:
        with open(ADMIN_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error saving admin config: {e}")

# Initialize globals from config
_config = load_admin_config()
ADMIN_EMAIL = _config.get('admin_email', 'admin@example.com')
ADMIN_ID = _config.get('admin_id', '6777153598')
ADMIN_PASSWORD = _config.get('admin_password', 'admin123')
BOT_TOKEN = os.getenv('BOT_TOKEN')

def get_sender_email():
    """Get the active company sender email from config"""
    cfg = load_admin_config()
    return cfg.get('sender_email', 'leehexchange@gmail.com')

def set_sender_email(email):
    """Save a new company sender email to config"""
    cfg = load_admin_config()
    cfg['sender_email'] = email
    save_admin_config(cfg)

# Crypto configurations
COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "POL": "polygon-ecosystem-token",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "DOGE": "dogecoin",
    "TRX": "tron",
    "TON": "the-open-network",
    "SUI": "sui"
}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            init_data = request.args.get('initData')
            if init_data:
                try:
                    if f'"id":{ADMIN_ID}' in init_data or f'"id": {ADMIN_ID}' in init_data:
                        session['logged_in'] = True
                        session['admin_email'] = ADMIN_EMAIL
                        session['is_super_admin'] = True
                        session['admin_permissions'] = SUPER_ADMIN_PERMISSIONS
                        session['admin_name'] = 'Super Admin'
                        session['admin_role_label'] = 'Super Admin'
                        return f(*args, **kwargs)
                except:
                    pass
            return redirect('/login')
        # Back-fill super-admin flag for existing sessions that pre-date multi-admin
        if 'is_super_admin' not in session:
            # Never promote an ambiguous session to super-admin. Older
            # super-admin sessions that contain the configured email can be
            # upgraded safely; anything else must authenticate again.
            if str(session.get('admin_email', '')).lower() != str(ADMIN_EMAIL).lower():
                session.clear()
                return redirect('/login')
            session['is_super_admin'] = True
            session['admin_permissions'] = SUPER_ADMIN_PERMISSIONS
            session['admin_name'] = 'Super Admin'
            session['admin_role_label'] = 'Super Admin'
        # Force-logout deleted sub-admins on every request
        if not session.get('is_super_admin', True):
            session['admin_permissions'] = [
                p for p in session.get('admin_permissions', [])
                if p != 'dashboard'
            ]
            sub_id = session.get('sub_admin_id')
            cfg = load_admin_config()
            still_active = any(
                a.get('id') == sub_id and a.get('status') == 'active'
                for a in cfg.get('sub_admins', [])
            )
            if not still_active:
                session.clear()
                return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    """Restrict route to super admin only."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect('/login')
        if not session.get('is_super_admin', False):
            return render_template('403.html'), 403
        return f(*args, **kwargs)
    return decorated_function

def has_permission(perm):
    """Check if the current session has a given permission."""
    if session.get('is_super_admin', False):
        return True
    return perm in session.get('admin_permissions', [])

def permission_required(*permissions):
    """Require a matching permission for a page or API endpoint."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get('is_super_admin', False):
                return f(*args, **kwargs)
            assigned = set(session.get('admin_permissions', []))
            if not assigned.intersection(permissions):
                if request.path.startswith('/api/'):
                    return jsonify({'success': False, 'error': 'Unauthorized'}), 403
                return redirect(get_first_allowed_page(assigned))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_first_allowed_page(permissions):
    """Return the first dashboard page a sub-admin is allowed to visit."""
    permissions = set(permissions or []) - {'dashboard'}
    ordered = [
        ('transactions',      '/transactions'),
        ('transactions_view', '/transactions'),
        ('giveaway',          '/giveaway-claims'),
        ('giveaway_view',     '/giveaway-claims'),
        ('broadcast',         '/broadcast'),
        ('emails',            '/emails'),
        ('users',             '/users'),
        ('rates',             '/crypto-rates'),
    ]
    for perm, page in ordered:
        if perm in permissions:
            return page
    return '/login'

# Transaction amounts are stored in several formats by the Telegram bot.
# Only explicit NGN values are safe to add to a Naira revenue total. USD
# values and crypto quantities do not contain a historical NGN settlement
# amount, so they must not be silently treated as Naira.
COMPLETED_TRANSACTION_STATUSES = {'approved', 'completed'}

def parse_naira_amount(value):
    """Extract the explicit Naira amount from a transaction amount string."""
    text = str(value or '')
    match = re.search(
        r'(?:₦|NGN\s*|(?<![A-Za-z])N\s*)'
        r'([0-9][0-9,]*(?:\.[0-9]+)?)',
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return 0.0
    try:
        return float(match.group(1).replace(',', ''))
    except (TypeError, ValueError):
        return 0.0

def parse_usd_amount(value):
    """Extract an explicit USD amount from a transaction amount string."""
    text = str(value or '')
    match = re.search(
        r'(?:\$\s*|USD\s*)'
        r'([0-9][0-9,]*(?:\.[0-9]+)?)',
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return 0.0
    try:
        return float(match.group(1).replace(',', ''))
    except (TypeError, ValueError):
        return 0.0

def transaction_currency_totals(tx, completed_only=True):
    """Return settled (NGN, USD) values represented by one transaction."""
    if str(tx.get('Type', '')).strip().lower() == 'user join':
        return 0.0, 0.0
    if completed_only and str(tx.get('Status', '')).strip().lower() not in COMPLETED_TRANSACTION_STATUSES:
        return 0.0, 0.0
    amount = tx.get('Amount', '')
    return parse_naira_amount(amount), parse_usd_amount(amount)

def transaction_totals(transactions, completed_only=True):
    """Aggregate settled transaction values without mixing currency units."""
    naira_total = 0.0
    usd_total = 0.0
    for tx in transactions:
        naira, usd = transaction_currency_totals(tx, completed_only=completed_only)
        naira_total += naira
        usd_total += usd
    return naira_total, usd_total

def transaction_revenue(tx, completed_only=True):
    """Return the settled Naira amount represented by one transaction."""
    return transaction_currency_totals(tx, completed_only=completed_only)[0]

def format_naira_total(amount):
    """Format a Naira dashboard total while keeping the existing compact style."""
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M"
    return f"{int(amount):,}"

def format_usd_total(amount):
    """Format a USD dashboard total with cents for auditability."""
    return f"{amount:,.2f}"

CRYPTO_ASSET_NAMES = {
    'BTC': 'Bitcoin',
    'ETH': 'Ethereum',
    'BNB': 'BNB',
    'SOL': 'Solana',
    'XRP': 'XRP',
    'DOGE': 'Dogecoin',
    'TRX': 'TRON',
    'TON': 'TON',
    'SUI': 'Sui',
    'POL': 'Polygon',
}

def extract_crypto_symbol(tx):
    """Find a supported crypto symbol in the stored coin/order fields."""
    fields = [
        str(tx.get('Coin', '') or ''),
        str(tx.get('Type', '') or ''),
    ]
    haystack = ' '.join(fields).upper()
    for symbol in sorted(CRYPTO_ASSET_NAMES, key=len, reverse=True):
        if re.search(rf'(?<![A-Z]){re.escape(symbol)}(?![A-Z])', haystack):
            return symbol
    return ''

def parse_leading_quantity(value):
    """Read an asset quantity from sell values such as '0.5 SOL'."""
    match = re.match(r'\s*([0-9][0-9,]*(?:\.[0-9]+)?)', str(value or ''))
    if not match:
        return 0.0
    try:
        return float(match.group(1).replace(',', ''))
    except (TypeError, ValueError):
        return 0.0

def crypto_volume_breakdown(transactions):
    """Summarize approved/completed crypto activity by traded asset."""
    grouped = {}
    for tx in transactions:
        symbol = extract_crypto_symbol(tx)
        if not symbol:
            continue
        if str(tx.get('Status', '')).strip().lower() not in COMPLETED_TRANSACTION_STATUSES:
            continue
        if str(tx.get('Type', '')).strip().lower() == 'user join':
            continue
        item = grouped.setdefault(symbol, {
            'symbol': symbol,
            'name': CRYPTO_ASSET_NAMES[symbol],
            'orders': 0,
            'buy_usd': 0.0,
            'sell_quantity': 0.0,
        })
        item['orders'] += 1
        if str(tx.get('Type', '')).strip().lower() == 'buy':
            item['buy_usd'] += parse_usd_amount(tx.get('Amount', ''))
        elif str(tx.get('Type', '')).strip().lower() == 'sell':
            item['sell_quantity'] += parse_leading_quantity(tx.get('Amount', ''))

    return sorted(
        [
            {
                **item,
                'buy_usd': round(item['buy_usd'], 2),
                'sell_quantity': round(item['sell_quantity'], 8),
            }
            for item in grouped.values()
        ],
        key=lambda item: (-item['orders'], item['symbol']),
    )

def valid_email_address(value):
    """Accept ordinary mailbox addresses and reject malformed recipients."""
    address = str(value or '').strip()
    if len(address) > 254:
        return ''
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', address):
        return ''
    return address

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        config = load_admin_config()

        # Check super admin
        if identifier == config.get('admin_email', ADMIN_EMAIL).lower() and password == config.get('admin_password', ADMIN_PASSWORD):
            session['logged_in'] = True
            session['admin_email'] = identifier
            session['is_super_admin'] = True
            session['admin_permissions'] = SUPER_ADMIN_PERMISSIONS
            session['admin_name'] = 'Super Admin'
            session['admin_role_label'] = 'Super Admin'
            session['sub_admin_id'] = None
            return redirect('/dashboard')

        # Check sub-admins (they log in with username or email they chose during invite acceptance)
        for sub in config.get('sub_admins', []):
            if sub.get('status') != 'active':
                continue
            if (sub.get('username', '').lower() == identifier or sub.get('login_email', '').lower() == identifier) and sub.get('password') == password:
                role_key = sub.get('role', '')
                role_info = ROLES.get(role_key, {})
                perms = sub.get('permissions', role_info.get('permissions', []))
                # The dashboard is reserved for the super admin even if an
                # older config file still contains the legacy dashboard grant.
                perms = [p for p in perms if p != 'dashboard']
                session['logged_in'] = True
                session['admin_email'] = sub.get('login_email', identifier)
                session['is_super_admin'] = False
                session['admin_permissions'] = perms
                session['admin_name'] = sub.get('name', sub.get('username', 'Admin'))
                session['admin_role_label'] = role_info.get('label', 'Team Admin')
                session['sub_admin_id'] = sub.get('id')
                return redirect(get_first_allowed_page(perms))

        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.context_processor
def inject_admin_ctx():
    """Make admin session info available in every template."""
    notif = 0
    try:
        txs = load_transactions()
        notif = len([t for t in txs if str(t.get('Status', 'Pending')).strip().lower() == 'pending'])
    except Exception:
        pass
    return {
        'is_super_admin': session.get('is_super_admin', False),
        'admin_permissions': session.get('admin_permissions', []),
        'admin_role_label': session.get('admin_role_label', 'Super Admin'),
        'current_admin_name': session.get('admin_name', 'Admin'),
        'notification_count': notif,
        'current_year': datetime.now().year,
    }

@app.route('/')
def index():
    return render_template('landing.html')

@app.route('/developers')
def developers():
    return render_template('developers.html')

@app.get('/healthz')
def health_check():
    """Process health endpoint used by the deployment supervisor."""
    return jsonify({'status': 'ok', 'service': 'leehexchange-dashboard'}), 200

@app.route('/admin')
def admin_redirect():
    if 'logged_in' in session:
        perms = session.get('admin_permissions', [])
        if session.get('is_super_admin', False):
            return redirect('/dashboard')
        return redirect(get_first_allowed_page(perms))
    return redirect('/login')

@app.route('/dashboard')
@login_required
@super_admin_required
def dashboard():
    """Main admin dashboard."""
    from datetime import timedelta

    transactions = load_transactions()
    giveaway_claims = load_giveaway_claims()

    # Greeting
    hour = datetime.now().hour
    if hour < 12:
        greeting = 'Good Morning'
    elif hour < 17:
        greeting = 'Good Afternoon'
    else:
        greeting = 'Good Evening'

    date_str = datetime.now().strftime('%b %d, %Y')

    total_transactions = len(transactions)
    total_giveaway_claims = len(giveaway_claims)

    # Status counts
    pending_count = len([t for t in transactions if str(t.get('Status', 'Pending')).strip().lower() == 'pending'])
    completed_count = len([t for t in transactions if str(t.get('Status', '')).strip().lower() in ['approved', 'completed']])
    failed_count = len([t for t in transactions if str(t.get('Status', '')).strip().lower() in ['rejected', 'failed']])

    total_naira_num, total_usd_num = transaction_totals(transactions)
    total_revenue = format_naira_total(total_naira_num)
    total_usd = format_usd_total(total_usd_num)
    combined_total = f"{total_naira_num + total_usd_num:,.2f}"

    # User count
    user_ids = set()
    for t in transactions:
        uid = t.get('UserID') or t.get('Username', '')
        if uid:
            user_ids.add(str(uid))
    user_count = len(user_ids) if user_ids else 0

    # Today / yesterday
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    today_str = today.strftime('%Y-%m-%d')
    yesterday_str = yesterday.strftime('%Y-%m-%d')

    today_txs = [t for t in transactions if str(t.get('Timestamp', ''))[:10] == today_str]
    yesterday_txs = [t for t in transactions if str(t.get('Timestamp', ''))[:10] == yesterday_str]
    today_count = len(today_txs)
    today_rev = sum(transaction_revenue(t) for t in today_txs)
    yest_rev  = sum(transaction_revenue(t) for t in yesterday_txs)

    revenue_change = round((today_rev - yest_rev) / yest_rev * 100, 1) if yest_rev > 0 else 0
    yest_count = len(yesterday_txs)
    today_change = round((today_count - yest_count) / yest_count * 100, 1) if yest_count > 0 else 12.5

    # 7-day chart
    days = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
    day_labels = [d.strftime('%b %d') for d in days]
    day_strs   = [d.strftime('%Y-%m-%d') for d in days]
    day_counts = {d: 0 for d in day_strs}
    day_rev    = {d: 0.0 for d in day_strs}
    type_counts: dict = {}

    for tx in transactions:
        ts = str(tx.get('Timestamp', ''))[:10]
        if ts in day_counts:
            day_counts[ts] += 1
            day_rev[ts] += transaction_revenue(tx)
        tx_type = tx.get('Type', 'Other')
        if tx_type and tx_type != 'User Join':
            type_counts[tx_type] = type_counts.get(tx_type, 0) + 1

    chart_counts  = [day_counts[d] for d in day_strs]
    chart_revenue = [int(day_rev[d]) for d in day_strs]

    # Crypto volume
    crypto_kw = ['btc','eth','bnb','sol','xrp','doge','trx','ton','sui','pol','usdt','crypto','coin']
    crypto_txs = [t for t in transactions if any(k in str(t.get('Type', '')).lower() for k in crypto_kw)]
    crypto_volume = f"{len(crypto_txs):,}"

    # Live transactions (last 5)
    now_dt = datetime.now()
    live_transactions = []
    for tx in reversed(transactions[-5:] if transactions else []):
        ts_str = str(tx.get('Timestamp', ''))
        try:
            tx_time = datetime.strptime(ts_str[:19], '%Y-%m-%d %H:%M:%S')
            diff = int((now_dt - tx_time).total_seconds())
            if diff < 60: time_ago = f"{diff}s ago"
            elif diff < 3600: time_ago = f"{diff//60}m ago"
            elif diff < 86400: time_ago = f"{diff//3600}h ago"
            else: time_ago = f"{diff//86400}d ago"
        except Exception:
            time_ago = "Just now"
        tl = str(tx.get('Type', '')).lower()
        if 'btc' in tl or 'bitcoin' in tl: asset = 'BTC'
        elif 'eth' in tl: asset = 'ETH'
        elif 'bnb' in tl: asset = 'BNB'
        elif 'sol' in tl: asset = 'SOL'
        elif 'usdt' in tl: asset = 'USDT'
        elif 'amazon' in tl: asset = 'Amazon GC'
        elif 'gift' in tl: asset = 'GiftCard'
        else: asset = tx.get('Type', 'Token')
        live_transactions.append({
            'type': tx.get('Type', 'Transfer'),
            'username': tx.get('Username', 'user'),
            'amount': tx.get('Amount', 'N/A'),
            'time_ago': time_ago,
            'asset': asset,
        })

    recent_transactions = list(reversed(transactions[-10:])) if transactions else []
    recent_claims = giveaway_claims[-10:] if giveaway_claims else []

    return render_template('dashboard.html',
        greeting=greeting,
        date_str=date_str,
        total_transactions=total_transactions,
        total_giveaway_claims=total_giveaway_claims,
        total_revenue=total_revenue,
        total_naira=total_revenue,
        total_usd=total_usd,
        combined_total=combined_total,
        pending_count=pending_count,
        completed_count=completed_count,
        failed_count=failed_count,
        today_count=today_count,
        user_count=user_count,
        revenue_change=revenue_change,
        today_change=today_change,
        crypto_volume=crypto_volume,
        recent_transactions=recent_transactions,
        recent_claims=recent_claims,
        live_transactions=live_transactions,
        chart_labels=day_labels,
        chart_counts=chart_counts,
        chart_revenue=chart_revenue,
        type_labels=list(type_counts.keys()),
        type_data=list(type_counts.values()),
    )

@app.route('/transactions')
@login_required
@permission_required('transactions', 'transactions_view')
def transactions_page():
    """View all transactions"""
    transactions = load_transactions()
    return render_template('transactions.html', transactions=transactions)

@app.route('/giveaway-claims')
@login_required
@permission_required('giveaway', 'giveaway_view')
def giveaway_claims_page():
    """View all giveaway claims"""
    claims = load_giveaway_claims()
    return render_template('giveaway_claims.html', claims=claims)

@app.route('/users')
@login_required
@permission_required('users')
def users_page():
    """View all bot users"""
    transactions = load_transactions()
    users_dict = {}
    for tx in transactions:
        user_id = tx.get('UserID')
        username = tx.get('Username', 'Unknown')
        if user_id and username:
            if user_id not in users_dict:
                users_dict[user_id] = {
                    'user_id': user_id,
                    'username': username,
                    'tx_count': 0,
                    'orders': 0,
                    'first_seen': tx.get('Timestamp', 'N/A')
                }
            users_dict[user_id]['tx_count'] += 1
            users_dict[user_id]['orders'] += 1
    users = list(users_dict.values())
    return render_template('users.html', users=users)

@app.route('/crypto-rates')
@login_required
@permission_required('rates')
def crypto_rates_page():
    """View live cryptocurrency rates"""
    cryptos = get_crypto_rates()
    return render_template('crypto_rates.html', cryptos=cryptos)

@app.route('/settings')
@login_required
@super_admin_required
def settings_page():
    """Admin settings page"""
    config = load_admin_config()
    sub_admins = config.get('sub_admins', [])
    return render_template(
        'settings.html',
        admin_id=config.get('admin_id', ADMIN_ID),
        admin_email=config.get('admin_email', ADMIN_EMAIL),
        sender_email=get_sender_email(),
        sub_admins=sub_admins,
        roles=ROLES,
        all_permissions=ALL_PERMISSIONS,
    )

# ─── Admin invite accept page ────────────────────────────────────────────────
@app.route('/admin-invite/<token>', methods=['GET', 'POST'])
def admin_invite(token):
    """Sub-admin accepts invite and sets their password."""
    config = load_admin_config()
    sub_admins = config.get('sub_admins', [])
    target = next((a for a in sub_admins if a.get('invite_token') == token and a.get('status') == 'pending'), None)
    if not target:
        return render_template('admin_invite.html', error='This invite link is invalid or has already been used.', token=token, admin=None)
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        login_email = request.form.get('login_email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if not username or not password:
            return render_template('admin_invite.html', error='Username and password are required.', token=token, admin=target)
        if password != confirm:
            return render_template('admin_invite.html', error='Passwords do not match.', token=token, admin=target)
        if len(password) < 6:
            return render_template('admin_invite.html', error='Password must be at least 6 characters.', token=token, admin=target)
        # Activate the account
        target['username'] = username
        target['login_email'] = login_email or ''
        target['password'] = password
        target['status'] = 'active'
        target['activated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        save_admin_config(config)
        return render_template('admin_invite.html', success=True, token=token, admin=target)
    return render_template('admin_invite.html', token=token, admin=target, error=None)

# ─── Add sub-admin API ────────────────────────────────────────────────────────
MAX_SUB_ADMINS = 3

@app.route('/api/add-admin', methods=['POST'])
@super_admin_required
def add_admin():
    """Create a new sub-admin and return an invite link."""
    data = request.get_json()
    name = data.get('name', '').strip()
    role_key = data.get('role', '').strip()
    if not name or role_key not in ROLES:
        return jsonify({'success': False, 'message': 'Name and a valid role are required.'})
    config = load_admin_config()
    current = config.get('sub_admins', [])
    if len(current) >= MAX_SUB_ADMINS:
        return jsonify({
            'success': False,
            'message': f'Admin limit reached. You can have at most {MAX_SUB_ADMINS} team admins.'
        })
    # Use custom permissions from UI if provided; otherwise fall back to role defaults
    # Dashboard access is intentionally not grantable to sub-admins.
    valid_perms = [p[0] for p in ALL_PERMISSIONS if p[0] != 'dashboard']
    custom_perms = data.get('permissions', None)
    if custom_perms and isinstance(custom_perms, list):
        permissions = [p for p in custom_perms if p in valid_perms]
    else:
        permissions = ROLES[role_key]['permissions']
    permissions = [p for p in permissions if p != 'dashboard']
    token = uuid.uuid4().hex
    new_admin = {
        'id': uuid.uuid4().hex,
        'name': name,
        'role': role_key,
        'permissions': permissions,
        'invite_token': token,
        'status': 'pending',
        'username': None,
        'login_email': None,
        'password': None,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'activated_at': None,
    }
    current.append(new_admin)
    config['sub_admins'] = current
    save_admin_config(config)
    base_url = request.host_url.rstrip('/')
    invite_link = f'{base_url}/admin-invite/{token}'
    return jsonify({'success': True, 'invite_link': invite_link, 'admin': new_admin})


@app.route('/api/check-session')
def check_session():
    """Quick endpoint for sub-admins to detect forced logout."""
    if 'logged_in' not in session:
        return jsonify({'valid': False})
    if session.get('is_super_admin', True):
        return jsonify({'valid': True})
    sub_id = session.get('sub_admin_id')
    cfg = load_admin_config()
    still_active = any(
        a.get('id') == sub_id and a.get('status') == 'active'
        for a in cfg.get('sub_admins', [])
    )
    if not still_active:
        session.clear()
        return jsonify({'valid': False})
    return jsonify({'valid': True})

# ─── Remove sub-admin API ─────────────────────────────────────────────────────
@app.route('/api/remove-admin', methods=['POST'])
@super_admin_required
def remove_admin():
    """Remove a sub-admin by ID."""
    data = request.get_json()
    admin_id = data.get('id', '').strip()
    if not admin_id:
        return jsonify({'success': False, 'message': 'Admin ID is required.'})
    config = load_admin_config()
    sub_admins = config.get('sub_admins', [])
    original_len = len(sub_admins)
    config['sub_admins'] = [a for a in sub_admins if a.get('id') != admin_id]
    if len(config['sub_admins']) == original_len:
        return jsonify({'success': False, 'message': 'Admin not found.'})
    save_admin_config(config)
    return jsonify({'success': True})

# ─── Regenerate invite link ────────────────────────────────────────────────────
@app.route('/api/regenerate-invite', methods=['POST'])
@super_admin_required
def regenerate_invite():
    """Generate a fresh invite token for a pending sub-admin."""
    data = request.get_json()
    admin_id = data.get('id', '').strip()
    config = load_admin_config()
    for sub in config.get('sub_admins', []):
        if sub.get('id') == admin_id and sub.get('status') == 'pending':
            sub['invite_token'] = uuid.uuid4().hex
            save_admin_config(config)
            base_url = request.host_url.rstrip('/')
            invite_link = f'{base_url}/admin-invite/{sub["invite_token"]}'
            return jsonify({'success': True, 'invite_link': invite_link})
    return jsonify({'success': False, 'message': 'Admin not found or already active.'})

@app.route('/emails')
@login_required
@permission_required('emails')
def emails_page():
    """View all sent email notifications and subscriber list"""
    emails = load_email_log()
    user_emails = load_user_emails()
    sender_email = get_sender_email()
    return render_template('emails.html', emails=emails, user_emails=user_emails, sender_email=sender_email)

@app.route('/api/send-email-blast', methods=['POST'])
@login_required
@permission_required('emails')
def send_email_blast():
    """Send email to selected subscribers"""
    data = request.get_json(silent=True) or {}
    raw_recipients = data.get('recipients', [])
    if not isinstance(raw_recipients, list):
        return jsonify({'success': False, 'message': 'Recipients must be a list of email addresses.'}), 400
    recipients = []
    invalid_recipients = []
    seen = set()
    for value in raw_recipients:
        recipient = valid_email_address(value)
        if not recipient:
            invalid_recipients.append(str(value or '').strip() or '(blank)')
        elif recipient.lower() not in seen:
            recipients.append(recipient)
            seen.add(recipient.lower())
    subject = data.get('subject', '').strip()
    body = data.get('body', '').strip()
    if invalid_recipients:
        return jsonify({
            'success': False,
            'message': f"Invalid email address(es): {', '.join(invalid_recipients[:3])}"
        }), 400
    if not recipients or not subject or not body:
        return jsonify({'success': False, 'message': 'Recipients, subject and body are required.'}), 400
    sent = 0
    failed = 0
    sender = get_sender_email()
    if not valid_email_address(sender):
        return jsonify({'success': False, 'message': 'The exchange sender email is not configured correctly.'}), 500
    for email in recipients:
        try:
            from replitmail import Mail
            mail = Mail()
            success = mail.send(to=str(email), subject=subject, body=body, from_email=sender)
            status = 'Sent' if success else 'Failed'
            log_email(email, subject, body, status)
            if success:
                sent += 1
            else:
                failed += 1
        except Exception as e:
            log_email(email, subject, body, 'Error')
            failed += 1
    return jsonify({'success': True, 'sent': sent, 'failed': failed, 'sender': sender})

@app.route('/api/delete-subscriber', methods=['POST'])
@login_required
@permission_required('emails')
def delete_subscriber():
    """Remove a subscriber from user_emails.csv by email address"""
    data = request.get_json()
    email = str(data.get('email', '')).strip()
    if not email:
        return jsonify({'success': False, 'message': 'Email is required.'})
    try:
        if not os.path.exists('user_emails.csv'):
            return jsonify({'success': False, 'message': 'Subscriber list not found.'})
        df = pd.read_csv('user_emails.csv')
        original_len = len(df)
        df = df[df['Email'].astype(str).str.strip() != email]
        if len(df) == original_len:
            return jsonify({'success': False, 'message': 'Subscriber not found.'})
        df.to_csv('user_emails.csv', index=False)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/broadcast', methods=['GET', 'POST'])
@login_required
@permission_required('broadcast')
def broadcast_page():
    """Broadcast notification to all users"""
    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        image_url = request.form.get('image_url', '').strip()
        image_file = request.files.get('image_file')
        
        # Handle file upload
        if image_file and image_file.filename != '':
            filename = f"broadcast_{datetime.now().strftime('%Y%m%d%H%M%S')}_{image_file.filename}"
            upload_path = os.path.join('static/uploads', filename)
            image_file.save(upload_path)
            # Use the local path or a URL that the bot can access
            # In Replit, we'll use the relative static path
            image_url = upload_path

        if not message and not image_url:
            return render_template('broadcast.html', error="Message or Image cannot be empty")
        
        try:
            with open('user_data.json', 'r') as f:
                user_data = json.load(f)
            
            users = user_data.get('users', {})
            success_count = 0
            
            # Create a broadcast object that can include an image
            broadcast_item = {
                "text": message,
                "image": image_url if image_url else None
            }
            
            for user_id in users:
                # Add to pending broadcasts for users to see ONLY on next /start
                if "pending_broadcasts" not in users[user_id]:
                    users[user_id]["pending_broadcasts"] = []
                
                # Check for duplicates to avoid spamming the same broadcast
                is_duplicate = False
                for existing in users[user_id]["pending_broadcasts"]:
                    if isinstance(existing, dict):
                        if existing.get('text') == message and existing.get('image') == image_url:
                            is_duplicate = True
                            break
                    elif existing == message and not image_url:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    users[user_id]["pending_broadcasts"].append(broadcast_item)
                
                success_count += 1
            
            # Save the updated pending broadcasts
            with open('user_data.json', 'w') as f:
                json.dump(user_data, f, indent=4)
            
            flash(f"Broadcast queued for {success_count} users. Information will be delivered ONLY when they trigger /start on the bot.", "success")
            return redirect(url_for('broadcast_page'))
        except Exception as e:
            flash(f"Error sending broadcast: {str(e)}", "danger")
            return redirect(url_for('broadcast_page'))
            
    return render_template('broadcast.html')

@app.route('/giveaway-tracking')
@login_required
@permission_required('giveaway', 'giveaway_view')
def giveaway_tracking_page():
    """View all giveaway codes — used and available — with generation UI"""
    try:
        with open('user_data.json', 'r') as f:
            user_data = json.load(f)
    except Exception:
        user_data = {}

    codes = user_data.get('giveaway_codes', {})
    all_codes = []
    for code, info in codes.items():
        all_codes.append({
            'code': code,
            'used': info.get('used', False),
            'used_by': info.get('used_by'),
            'used_at': info.get('used_at', ''),
        })
    # Used codes first (most recent), then available
    all_codes.sort(key=lambda x: (not x['used'], x.get('used_at') or ''), reverse=True)

    total     = len(all_codes)
    used_cnt  = sum(1 for c in all_codes if c['used'])
    avail_cnt = total - used_cnt

    return render_template('giveaway_tracking.html',
        all_codes=all_codes,
        total=total,
        used_cnt=used_cnt,
        avail_cnt=avail_cnt,
        is_super_admin=(session.get('admin_type') == 'super'),
    )


@app.route('/api/generate-codes', methods=['POST'])
@super_admin_required
def api_generate_codes():
    """Generate a fresh batch of LEEH giveaway codes."""
    import random, string as _str
    data = request.get_json() or {}
    try:
        count = max(1, min(int(data.get('count', 10)), 100))
    except (ValueError, TypeError):
        count = 10

    def gen_code():
        chars = _str.ascii_lowercase + _str.digits
        return f"leeh-{''.join(random.choices(chars, k=4))}-{''.join(random.choices(chars, k=4))}"

    try:
        with open('user_data.json', 'r') as f:
            user_data = json.load(f)
    except Exception:
        user_data = {}

    codes = user_data.setdefault('giveaway_codes', {})
    new_codes = []
    attempts = 0
    while len(new_codes) < count and attempts < count * 20:
        c = gen_code()
        if c not in codes:
            codes[c] = {'used': False, 'used_by': None, 'used_at': None}
            new_codes.append(c)
        attempts += 1

    user_data['giveaway_codes'] = codes
    with open('user_data.json', 'w') as f:
        json.dump(user_data, f, indent=4)

    return jsonify({'success': True, 'generated': len(new_codes), 'codes': new_codes})

@app.route('/api/crypto-rates')
@login_required
@permission_required('rates')
def api_crypto_rates():
    """Get crypto rates from CoinGecko"""
    cryptos = get_crypto_rates()
    return jsonify({'success': True, 'data': cryptos})

@app.route('/api/change-password', methods=['POST'])
@login_required
@super_admin_required
def change_password():
    """Change admin password"""
    current = request.form.get('current_password', '')
    new = request.form.get('new_password', '')
    confirm = request.form.get('confirm_password', '')
    
    global ADMIN_PASSWORD, ADMIN_EMAIL, ADMIN_ID
    
    if not current or not new or not confirm:
        return jsonify({'success': False, 'message': 'All fields are required'})
    if current != ADMIN_PASSWORD:
        return jsonify({'success': False, 'message': 'Current password is incorrect'})
    if new != confirm:
        return jsonify({'success': False, 'message': 'New passwords do not match'})
    if len(new) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters'})
    
    ADMIN_PASSWORD = new
    cfg = load_admin_config()
    cfg['admin_password'] = ADMIN_PASSWORD
    save_admin_config(cfg)
    return jsonify({'success': True, 'message': 'Password changed successfully'})

@app.route('/api/set-sender-email', methods=['POST'])
@login_required
@super_admin_required
def api_set_sender_email():
    """Save company sender email"""
    import re
    data = request.get_json()
    email = (data.get('email') or '').strip()
    if not email:
        return jsonify({'success': False, 'message': 'Email address is required.'})
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({'success': False, 'message': 'Please enter a valid email address.'})
    set_sender_email(email)
    return jsonify({'success': True, 'message': f'Sender email updated to {email}', 'email': email})

@app.route('/api/transfer-ownership', methods=['POST'])
@login_required
@super_admin_required
def transfer_ownership():
    """Transfer admin ownership to a new admin"""
    data = request.json
    current_password = data.get('current_password', '')
    old_admin_email = data.get('old_admin_email', '').strip()
    new_admin_email = data.get('new_admin_email', '').strip()
    new_admin_id = data.get('new_admin_id', '').strip()
    
    global ADMIN_PASSWORD, ADMIN_ID, ADMIN_EMAIL
    
    if not current_password or not new_admin_email or not new_admin_id or not old_admin_email:
        return jsonify({'success': False, 'message': 'All fields are required'})
    
    if current_password != ADMIN_PASSWORD:
        return jsonify({'success': False, 'message': 'Current password is incorrect'})
    
    if '@' not in old_admin_email or '@' not in new_admin_email:
        return jsonify({'success': False, 'message': 'Invalid email address'})
    
    if not new_admin_id.isdigit():
        return jsonify({'success': False, 'message': 'Invalid Telegram User ID'})
    
    # Store old values for logging and email
    previous_admin_id = ADMIN_ID
    previous_admin_email = ADMIN_EMAIL
    
    # Update system to reflect new admin as active owner
    ADMIN_ID = new_admin_id
    ADMIN_EMAIL = new_admin_email
    
    # Save to persistent config
    save_admin_config({
        "admin_email": ADMIN_EMAIL,
        "admin_id": ADMIN_ID,
        "admin_password": ADMIN_PASSWORD
    })
    
    # Send professional notification emails
    try:
        from replitmail import Mail
        mail = Mail()
        dashboard_url = os.getenv('REPL_SLUG') + "." + os.getenv('REPL_OWNER', 'user') + ".repl.co"

        # 1. Email to Old Admin
        old_email_subject = "LEEH Exchange – Administrative Rights Revoked"
        old_email_body = (
            f"Hello,\n\n"
            f"This email confirms that your administrative rights for LEEH Exchange Dashboard have been officially revoked.\n\n"
            f"Administrative control has been transferred to: {new_admin_email}\n"
            f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"You will no longer be able to log in with your previous credentials. If you believe this was an error, please contact the system owner.\n\n"
            f"Thank you for your service.\n"
            f"LEEH Exchange Security Team"
        )
        mail.send(to=old_admin_email, subject=old_email_subject, body=old_email_body)

        # 2. Email to New Admin
        email_subject = "Admin Ownership Transfer – Immediate Action Required"
        email_body = (
            f"Hello,\n\n"
            f"You have been officially assigned as the new administrator for LEEH Exchange Dashboard.\n\n"
            f"--- CONFIDENTIAL ACCESS DETAILS ---\n"
            f"Admin Role: Owner (Full Privileges)\n"
            f"Login Email: {new_admin_email}\n"
            f"Temporary Password: {ADMIN_PASSWORD}\n"
            f"Dashboard Link: https://{dashboard_url}\n\n"
            f"--- ONBOARDING NOTE ---\n"
            f"You now have full administrative control over the platform, including transaction monitoring, "
            f"giveaway management, and user oversight. Please log in with the email address provided above. "
            f"Please log in immediately and change your password in the Settings section to secure your account.\n\n"
            f"This is an automated security notification.\n"
            f"LEEH Exchange Security Team"
        )
        mail.send(to=new_admin_email, subject=email_subject, body=email_body)
        
        # Log the activity
        from csv_handler import log_admin_activity
        log_admin_activity("OWNERSHIP_TRANSFER", f"From {previous_admin_id} to {new_admin_id} ({new_admin_email})")
        
        # Send Telegram notification for confirmation
        transfer_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        telegram_notification = (
            f"👑 **Ownership Transfer Completed**\n\n"
            f"The dashboard has been successfully transferred.\n"
            f"New Admin Email: {new_admin_email}\n"
            f"New Admin ID: {new_admin_id}\n"
            f"Timestamp: {transfer_timestamp}\n\n"
            f"Your administrative rights have been revoked."
        )
        send_user_notification(previous_admin_id, telegram_notification)
        send_user_notification(new_admin_id, f"🎉 **Welcome New Admin**\n\nControl transferred to you at {transfer_timestamp}.\nCheck your email for access credentials.")

    except Exception as e:
        print(f"Error in transfer workflow: {e}")
        return jsonify({'success': False, 'message': f'Transfer initiated but encountered an error sending emails: {str(e)}'})
    
    # Revoke session for previous admin
    session.clear()
    
    return jsonify({'success': True, 'message': 'Ownership successfully transferred. Confirmation emails have been sent to both parties.'})

@app.route('/api/transactions', methods=['GET'])
@login_required
@permission_required('transactions', 'transactions_view')
def api_transactions():
    """API endpoint for transactions"""
    try:
        transactions = load_transactions()
        return jsonify({
            'success': True,
            'count': len(transactions),
            'data': transactions
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/giveaway-claims', methods=['GET'])
@login_required
@permission_required('giveaway', 'giveaway_view')
def api_giveaway_claims():
    """API endpoint for giveaway claims"""
    try:
        claims = load_giveaway_claims()
        return jsonify({
            'success': True,
            'count': len(claims),
            'data': claims
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
@login_required
@super_admin_required
def api_stats():
    """Get dashboard statistics"""
    try:
        transactions = load_transactions()
        claims = load_giveaway_claims()
        
        stats = {
            'total_transactions': len(transactions),
            'total_giveaway_claims': len(claims),
            'transaction_types': {},
            'networks': {}
        }
        
        for tx in transactions:
            tx_type = tx.get('Order_Type', 'Unknown')
            stats['transaction_types'][tx_type] = stats['transaction_types'].get(tx_type, 0) + 1
        
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/transaction/approve', methods=['POST'])
@login_required
@permission_required('transactions')
def approve_transaction():
    """Approve a transaction"""
    try:
        data = request.json
        timestamp = data.get('timestamp')
        user_id = data.get('user_id')
        user_email = get_transaction_email(timestamp, user_id)
        
        if update_transaction_status(timestamp, user_id, 'Approved'):
            telegram_msg = (
                "✅ Order Approved!\n\n"
                "Great news! Your transaction has been approved and is now being processed.\n\n"
                f"Transaction Reference: {timestamp}\n\n"
                "Your crypto will be delivered to your wallet shortly. "
                "We appreciate your trust in LEEH Exchange!\n\n"
                "Ready to trade again? Visit us at https://t.me/LeehExchangeBot"
            )
            send_user_notification(user_id, telegram_msg)

            email_body = (
                "Hello,\n\n"
                "Great news! Your LEEH Exchange order has been approved.\n\n"
                f"Transaction Reference: {timestamp}\n"
                "Status: APPROVED\n\n"
                "Your crypto will be delivered to your wallet shortly. "
                "We truly appreciate you choosing LEEH Exchange for your cryptocurrency needs.\n\n"
                "Looking to make another trade? We've got you covered with the best rates!\n"
                "Start trading now: https://t.me/LeehExchangeBot\n\n"
                "Thank you for being a valued member of the LEEH Exchange community.\n\n"
                "Best regards,\n"
                "The LEEH Exchange Team"
            )
            send_email_notification(user_email, "Your LEEH Exchange Order Has Been Approved!", email_body)

            return jsonify({'success': True, 'message': 'Transaction approved'})
        return jsonify({'success': False, 'error': 'Transaction not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/transaction/reject', methods=['POST'])
@login_required
@permission_required('transactions')
def reject_transaction():
    """Reject a transaction"""
    try:
        data = request.json
        timestamp = data.get('timestamp')
        user_id = data.get('user_id')
        reason = data.get('reason', 'No reason provided')
        user_email = get_transaction_email(timestamp, user_id)
        
        if update_transaction_status(timestamp, user_id, 'Rejected'):
            telegram_msg = (
                "❌ Order Update\n\n"
                f"Unfortunately, your recent order could not be processed.\n\n"
                f"Reason: {reason}\n"
                f"Transaction Reference: {timestamp}\n\n"
                "If you have any questions or need assistance, please reach out to our support team.\n\n"
                "Try again: https://t.me/LeehExchangeBot"
            )
            send_user_notification(user_id, telegram_msg)

            email_body = (
                "Hello,\n\n"
                "We regret to inform you that your recent LEEH Exchange order could not be processed.\n\n"
                f"Transaction Reference: {timestamp}\n"
                "Status: REJECTED\n\n"
                f"Reason: {reason}\n\n"
                "If you believe this is an error or need further clarification, please don't hesitate to contact our support team by messaging us on Telegram.\n\n"
                "You're welcome to place a new order at any time:\n"
                "https://t.me/LeehExchangeBot\n\n"
                "We apologize for any inconvenience and hope to serve you better on your next transaction.\n\n"
                "Best regards,\n"
                "The LEEH Exchange Team"
            )
            send_email_notification(user_email, "Update on Your LEEH Exchange Order", email_body)

            return jsonify({'success': True, 'message': 'Transaction rejected'})
        return jsonify({'success': False, 'error': 'Transaction not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/transaction/pending', methods=['POST'])
@login_required
@permission_required('transactions')
def pending_transaction():
    """Keep transaction as pending"""
    try:
        data = request.json
        timestamp = data.get('timestamp')
        user_id = data.get('user_id')
        
        if update_transaction_status(timestamp, user_id, 'Pending'):
            send_user_notification(user_id, 
                f"⏳ **Order Status: Pending**\n\n"
                f"Your order is under review.\n"
                f"Transaction: {timestamp}\n\n"
                f"We'll notify you when it's processed.")
            return jsonify({'success': True, 'message': 'Transaction set to pending'})
        return jsonify({'success': False, 'error': 'Transaction not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/transaction/bulk-approve', methods=['POST'])
@login_required
@permission_required('transactions')
def bulk_approve():
    """Approve multiple transactions"""
    try:
        data = request.json
        transactions = data.get('transactions', [])
        count = 0
        
        for tx in transactions:
            timestamp = tx.get('timestamp')
            user_id = tx.get('user_id')
            user_email = get_transaction_email(timestamp, user_id)
            
            if update_transaction_status(timestamp, user_id, 'Approved'):
                telegram_msg = (
                    "✅ Order Approved!\n\n"
                    "Great news! Your transaction has been approved and is now being processed.\n\n"
                    f"Transaction Reference: {timestamp}\n\n"
                    "Your crypto will be delivered to your wallet shortly. "
                    "We appreciate your trust in LEEH Exchange!\n\n"
                    "Ready to trade again? Visit us at https://t.me/LeehExchangeBot"
                )
                send_user_notification(user_id, telegram_msg)
                email_body = (
                    "Hello,\n\n"
                    "Great news! Your LEEH Exchange order has been approved.\n\n"
                    f"Transaction Reference: {timestamp}\n"
                    "Status: APPROVED\n\n"
                    "Your crypto will be delivered to your wallet shortly. "
                    "We truly appreciate you choosing LEEH Exchange.\n\n"
                    "Ready to trade again? https://t.me/LeehExchangeBot\n\n"
                    "Best regards,\nThe LEEH Exchange Team"
                )
                send_email_notification(user_email, "Your LEEH Exchange Order Has Been Approved!", email_body)
                count += 1
        
        return jsonify({'success': True, 'message': f'{count} transactions approved', 'count': count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/transaction/bulk-reject', methods=['POST'])
@login_required
@permission_required('transactions')
def bulk_reject():
    """Reject multiple transactions"""
    try:
        data = request.json
        transactions = data.get('transactions', [])
        reason = data.get('reason', 'No reason provided')
        count = 0
        
        for tx in transactions:
            timestamp = tx.get('timestamp')
            user_id = tx.get('user_id')
            user_email = get_transaction_email(timestamp, user_id)
            
            if update_transaction_status(timestamp, user_id, 'Rejected'):
                telegram_msg = (
                    "❌ Order Update\n\n"
                    f"Unfortunately, your recent order could not be processed.\n\n"
                    f"Reason: {reason}\n"
                    f"Transaction Reference: {timestamp}\n\n"
                    "If you need help, contact us at https://t.me/LeehExchangeBot"
                )
                send_user_notification(user_id, telegram_msg)
                email_body = (
                    "Hello,\n\n"
                    "We regret to inform you that your recent order could not be processed.\n\n"
                    f"Transaction Reference: {timestamp}\n"
                    "Status: REJECTED\n\n"
                    f"Reason: {reason}\n\n"
                    "You're welcome to place a new order at any time:\n"
                    "https://t.me/LeehExchangeBot\n\n"
                    "Best regards,\nThe LEEH Exchange Team"
                )
                send_email_notification(user_email, "Update on Your LEEH Exchange Order", email_body)
                count += 1
        
        return jsonify({'success': True, 'message': f'{count} transactions rejected', 'count': count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/transaction/bulk-pending', methods=['POST'])
@login_required
@permission_required('transactions')
def bulk_pending():
    """Set multiple transactions as pending"""
    try:
        data = request.json
        transactions = data.get('transactions', [])
        count = 0
        
        for tx in transactions:
            timestamp = tx.get('timestamp')
            user_id = tx.get('user_id')
            
            if update_transaction_status(timestamp, user_id, 'Pending'):
                send_user_notification(user_id, 
                    f"⏳ **Order Status: Pending**\n\n"
                    f"Your order is under review.\n"
                    f"Transaction: {timestamp}\n\n"
                    f"We'll notify you when it's processed.")
                count += 1
        
        return jsonify({'success': True, 'message': f'{count} transactions set to pending', 'count': count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def load_transactions():
    """Load transactions from CSV with status"""
    try:
        if not os.path.exists('transactions.csv'):
            return []
        df = pd.read_csv('transactions.csv')
        if 'Status' not in df.columns:
            df['Status'] = 'Pending'
            df.to_csv('transactions.csv', index=False)
        if 'Email' not in df.columns:
            df['Email'] = ''
            df.to_csv('transactions.csv', index=False)
        return df.to_dict('records')
    except Exception as e:
        print(f"Error loading transactions: {e}")
        return []

def send_user_notification(user_id, message):
    """Send Telegram notification to user"""
    try:
        url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
        payload = {'chat_id': user_id, 'text': message, 'parse_mode': 'Markdown'}
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Error sending notification: {e}")

EMAIL_LOG_FILE = 'email_log.csv'

def log_email(to_email, subject, body, status):
    """Log sent email to CSV file"""
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        file_exists = os.path.exists(EMAIL_LOG_FILE)
        with open(EMAIL_LOG_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['Timestamp', 'To', 'Subject', 'Body', 'Status'])
            if not file_exists:
                writer.writeheader()
            writer.writerow({
                'Timestamp': timestamp,
                'To': to_email,
                'Subject': subject,
                'Body': body,
                'Status': status
            })
    except Exception as e:
        print(f"Error logging email: {e}")

def send_email_notification(to_email, subject, body):
    """Send email notification to user using replitmail"""
    if not to_email or '@' not in str(to_email):
        print(f"Skipping email — invalid address: {to_email}")
        return
    try:
        from replitmail import Mail
        mail = Mail()
        sender = get_sender_email()
        success = mail.send(to=str(to_email), subject=subject, body=body, from_email=sender)
        status = 'Sent' if success else 'Failed'
        print(f"✅ Email {status} to {to_email} (from {sender})")
        log_email(to_email, subject, body, status)
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")
        log_email(to_email, subject, body, 'Error')

def load_user_emails():
    """Load subscriber email list from user_emails.csv"""
    try:
        if not os.path.exists('user_emails.csv'):
            return []
        df = pd.read_csv('user_emails.csv')
        return df.fillna('').to_dict('records')
    except Exception as e:
        print(f"Error loading user emails: {e}")
        return []

def load_email_log():
    """Load email log from CSV"""
    try:
        if not os.path.exists(EMAIL_LOG_FILE):
            return []
        df = pd.read_csv(EMAIL_LOG_FILE)
        records = df.fillna('').to_dict('records')
        return list(reversed(records))
    except Exception as e:
        print(f"Error loading email log: {e}")
        return []

def get_transaction_email(timestamp, user_id):
    """Retrieve stored email for a given transaction"""
    try:
        if not os.path.exists('transactions.csv'):
            return ''
        df = pd.read_csv('transactions.csv')
        if 'Email' not in df.columns:
            return ''
        mask = (df['Timestamp'].astype(str).str.strip() == str(timestamp).strip()) & \
               (df['UserID'].astype(str) == str(user_id))
        rows = df[mask]
        if not rows.empty:
            val = str(rows.iloc[0].get('Email', '')).strip()
            return '' if val.lower() in ('nan', 'none', '') else val
    except Exception as e:
        print(f"Error getting email: {e}")
    return ''

def update_transaction_status(timestamp, user_id, new_status):
    """Update transaction status in CSV"""
    try:
        if not os.path.exists('transactions.csv'):
            return False
        
        df = pd.read_csv('transactions.csv')
        if 'Status' not in df.columns:
            df['Status'] = 'Pending'
        if 'Email' not in df.columns:
            df['Email'] = ''
        
        mask = (df['Timestamp'].astype(str).str.strip() == str(timestamp).strip()) & \
               (df['UserID'].astype(str) == str(user_id))
        
        if mask.any():
            df.loc[mask, 'Status'] = new_status
            df.to_csv('transactions.csv', index=False)
            print(f"✅ Updated transaction status to {new_status}")
            return True
        else:
            print(f"❌ Transaction not found: timestamp={timestamp}, user_id={user_id}")
            return False
    except Exception as e:
        print(f"Error updating transaction: {e}")
        return False

def load_giveaway_claims():
    """Load giveaway claims from CSV"""
    try:
        if not os.path.exists('giveaway_claims.csv'):
            return []
        df = pd.read_csv('giveaway_claims.csv')
        return df.to_dict('records')
    except Exception as e:
        print(f"Error loading giveaway claims: {e}")
        return []

def get_crypto_rates():
    """Fetch cryptocurrency rates from CoinGecko API"""
    try:
        ids = ','.join(COINGECKO_IDS.values())
        url = f'https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd'
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            prices = response.json()
            cryptos = []
            for symbol, coingecko_id in COINGECKO_IDS.items():
                price = prices.get(coingecko_id, {}).get('usd', 'N/A')
                cryptos.append({
                    'symbol': symbol,
                    'name': coingecko_id.replace('-', ' ').title(),
                    'price': price
                })
            return cryptos
    except Exception as e:
        print(f"Error fetching crypto rates: {e}")
    
    return [{'symbol': s, 'name': n.replace('-', ' ').title(), 'price': 'N/A'} 
            for s, n in COINGECKO_IDS.items()]

@app.template_filter('format_timestamp')
def format_timestamp(value):
    if not value:
        return 'N/A'
    try:
        return datetime.strptime(str(value), '%Y-%m-%d %H:%M:%S').strftime('%b %d, %Y %I:%M %p')
    except:
        return str(value)

# ─── Team Chat ───────────────────────────────────────────────────────────────
CHAT_MESSAGES_FILE = 'chat_messages.json'
_chat_online = {}   # {admin_name: last_seen_timestamp}

def load_chat_messages():
    if os.path.exists(CHAT_MESSAGES_FILE):
        try:
            with open(CHAT_MESSAGES_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_chat_messages(msgs):
    try:
        with open(CHAT_MESSAGES_FILE, 'w') as f:
            json.dump(msgs, f, indent=2)
    except Exception as e:
        print(f"Chat save error: {e}")

def chat_online_count():
    now = datetime.utcnow().timestamp()
    return sum(1 for ts in _chat_online.values() if now - ts < 30)

@app.route('/chat')
@login_required
@super_admin_required
def chat_page():
    # Mark this admin as online
    _chat_online[session.get('admin_name', 'Admin')] = datetime.utcnow().timestamp()
    return render_template('chat.html')

@app.route('/api/chat/messages')
@login_required
@super_admin_required
def api_chat_messages():
    # Mark online
    _chat_online[session.get('admin_name', 'Admin')] = datetime.utcnow().timestamp()

    since = request.args.get('since', 0, type=int)
    msgs  = load_chat_messages()

    if since:
        msgs = [m for m in msgs if m['id'] > since]
    else:
        # Initial load — return last 60 messages
        msgs = msgs[-60:]

    return jsonify({'messages': msgs, 'online': chat_online_count()})

@app.route('/api/chat/send', methods=['POST'])
@login_required
@super_admin_required
def api_chat_send():
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()[:600]
    if not text:
        return jsonify({'error': 'empty'}), 400

    name = session.get('admin_name', 'Admin')
    role = session.get('admin_role_label', 'Admin')
    _chat_online[name] = datetime.utcnow().timestamp()

    msgs = load_chat_messages()
    new_id = (msgs[-1]['id'] + 1) if msgs else 1

    msg = {
        'id':        new_id,
        'sender':    name,
        'role':      role,
        'text':      text,
        'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S'),
        'reactions': {}
    }
    msgs.append(msg)
    # Keep only last 500 messages
    if len(msgs) > 500:
        msgs = msgs[-500:]
    save_chat_messages(msgs)
    return jsonify({'ok': True, 'message': msg})

@app.route('/api/chat/react', methods=['POST'])
@login_required
@super_admin_required
def api_chat_react():
    data   = request.get_json(silent=True) or {}
    msg_id = data.get('msg_id')
    emoji  = (data.get('emoji') or '').strip()
    if not msg_id or not emoji:
        return jsonify({'error': 'bad request'}), 400

    msgs = load_chat_messages()
    for m in msgs:
        if m['id'] == msg_id:
            reactions = m.setdefault('reactions', {})
            reactions[emoji] = reactions.get(emoji, 0) + 1
            break
    save_chat_messages(msgs)
    return jsonify({'ok': True})

# ══════════════════════════════════════════════════════
#  API KEY SYSTEM
# ══════════════════════════════════════════════════════
import secrets

API_KEYS_FILE = 'api_keys.json'

def load_api_keys():
    if os.path.exists(API_KEYS_FILE):
        try:
            with open(API_KEYS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_api_keys(keys):
    try:
        with open(API_KEYS_FILE, 'w') as f:
            json.dump(keys, f, indent=2)
    except Exception as e:
        print(f"Error saving api keys: {e}")

@app.route('/api/generate-key', methods=['POST'])
def generate_api_key():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    if not email or '@' not in email or '.' not in email.split('@')[-1]:
        return jsonify({'error': 'A valid email address is required'}), 400
    keys = load_api_keys()
    existing = next((k for k in keys if k.get('email') == email), None)
    if existing:
        return jsonify({
            'key': existing['key'],
            'email': email,
            'tier': existing.get('tier', 'free'),
            'created_at': existing.get('created_at', ''),
            'last_copied': existing.get('last_copied'),
            'existing': True
        })
    new_key = 'lx_free_' + secrets.token_hex(20)
    record = {
        'email': email,
        'key': new_key,
        'tier': 'free',
        'created_at': datetime.now().isoformat(),
        'last_copied': None,
    }
    keys.append(record)
    save_api_keys(keys)
    return jsonify({
        'key': new_key,
        'email': email,
        'tier': 'free',
        'created_at': record['created_at'],
        'last_copied': None,
        'existing': False
    })

@app.route('/api/copy-key', methods=['POST'])
def copy_api_key():
    from datetime import timedelta
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    keys = load_api_keys()
    record = next((k for k in keys if k.get('email') == email), None)
    if not record:
        return jsonify({'error': 'Key not found. Please generate a key first.'}), 404
    last_copied = record.get('last_copied')
    if last_copied:
        try:
            last_dt = datetime.fromisoformat(last_copied)
            days_since = (datetime.now() - last_dt).total_seconds() / 86400
            if days_since < 7:
                next_copy = last_dt + timedelta(days=7)
                days_left = max(1, 7 - int(days_since))
                return jsonify({
                    'error': 'Rate limited',
                    'message': f'You can copy your key again on {next_copy.strftime("%B %d, %Y")} ({days_left} day{"s" if days_left != 1 else ""} remaining)',
                    'days_remaining': days_left
                }), 429
        except Exception:
            pass
    record['last_copied'] = datetime.now().isoformat()
    save_api_keys(keys)
    return jsonify({'success': True, 'key': record['key']})

# ══════════════════════════════════════════════════════
#  VENORA MINI — IN-DASHBOARD AI ASSISTANT
# ══════════════════════════════════════════════════════

VENORA_MINI_KB = [
    {
        'keywords': ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'greet', 'start'],
        'response': "Hi! I'm **Venora Mini** 👋 — your LEEH Exchange dashboard assistant.\n\nI can help you with:\n• Approving or rejecting transactions\n• Managing giveaway claims\n• Understanding user activity\n• Navigating settings & admin roles\n• Anything about the dashboard\n\nWhat would you like to know?"
    },
    {
        'keywords': ['dashboard', 'home', 'overview', 'stats', 'statistics', 'summary', 'main page'],
        'response': "**Dashboard Overview** 📊\n\nThe dashboard is your control center. It shows:\n\n• **Total Transactions** — all buy/sell/gift card/airtime orders ever placed\n• **Giveaway Claims** — total LEEH code redemptions\n• **Active Users** — unique Telegram users who've used the bot\n• **Recent Activity** — the latest 10 transactions and giveaway claims at a glance\n\nAll stats are live — just refresh the page to update them."
    },
    {
        'keywords': ['transaction', 'transactions', 'order', 'orders', 'buy', 'sell', 'crypto order', 'gift card order', 'airtime order'],
        'response': "**Transactions Page** 💳\n\nThis page lists every customer order. Here's what you can do:\n\n**Single Actions:**\n✅ **Approve** — Mark the order as completed (payment confirmed)\n❌ **Reject** — Decline the order (invalid payment, fraud, etc.)\n🕐 **Pending** — Put it back to pending state for review\n\n**Bulk Actions:**\n1. Check the boxes beside multiple rows\n2. A blue action toolbar appears at the top\n3. Choose **Bulk Approve**, **Bulk Reject**, or **Bulk Pending**\n\n**Search:** Use the search bar to find orders by customer name, coin, type, or order ID.\n\n**Status Colors:**\n🟢 Green = Approved | 🔴 Red = Rejected | 🟡 Yellow = Pending"
    },
    {
        'keywords': ['approve', 'approving', 'how to approve', 'confirm order', 'mark approved'],
        'response': "**Approving a Transaction** ✅\n\n**Single approval:**\n1. Go to the **Transactions** page\n2. Find the order (search by name or scroll)\n3. Click the green **Approve** button on that row\n4. The status updates to Approved immediately\n\n**Bulk approval:**\n1. Check the checkbox on each row you want to approve\n2. The blue bulk-action toolbar appears at the top\n3. Click **Bulk Approve**\n4. All selected orders are approved at once\n\nThe customer will receive a Telegram notification when their order is approved."
    },
    {
        'keywords': ['reject', 'rejecting', 'how to reject', 'decline order', 'cancel order'],
        'response': "**Rejecting a Transaction** ❌\n\n**Single rejection:**\n1. Go to the **Transactions** page\n2. Find the order you want to reject\n3. Click the red **Reject** button on that row\n4. The status changes to Rejected\n\n**Bulk rejection:**\n1. Select multiple rows using the checkboxes\n2. Click **Bulk Reject** from the toolbar\n\nRejected orders stay in the system for records but are no longer active. The customer is notified via Telegram."
    },
    {
        'keywords': ['giveaway', 'giveaway claims', 'leeh code', 'codes', 'claim', 'promo'],
        'response': "**Giveaway Claims** 🎁\n\nThis section shows all LEEH promo code redemptions by bot users.\n\n**What you see:**\n• LEEH code used\n• Username and Telegram ID of the claimer\n• Date and time of the claim\n• Verification status (pending/verified)\n\n**Search:** Use the search bar to find a specific code or username instantly.\n\n**Use case:** When you run a giveaway (e.g. on social media), users claim the code inside the bot. You verify each claim here before the discount is applied to their next order."
    },
    {
        'keywords': ['users', 'user', 'bot users', 'customers', 'user list', 'who uses', 'activity'],
        'response': "**Users Page** 👥\n\nThis shows every Telegram user who has ever interacted with the bot.\n\n**Columns shown:**\n• Telegram username & ID\n• First seen (join date)\n• Total orders placed\n• Points balance\n• Last active timestamp\n\n**Note:** This is a **read-only** view. You cannot modify user data from the dashboard — changes to user accounts happen through the bot itself.\n\n**Search:** Filter users by username or Telegram ID using the search bar."
    },
    {
        'keywords': ['crypto rates', 'rates', 'prices', 'live prices', 'coingecko', 'price feed', 'btc price', 'eth price'],
        'response': "**Crypto Rates Page** 📈\n\nThis page shows live prices for all 10 supported coins, fetched directly from the **CoinGecko API**.\n\n**What's shown:**\n• Current USD price\n• NGN equivalent at current rate\n• 24-hour price change (%)\n• Market cap rank\n\n**Auto-refresh:** Rates automatically update every **60 seconds**. You can also click the Refresh button manually.\n\nThe same rate feed powers the bot's live price quotes to users."
    },
    {
        'keywords': ['settings', 'setting', 'password', 'change password', 'admin password'],
        'response': "**Settings — Password Change** 🔒\n\nTo change your admin password:\n1. Go to **Settings** in the sidebar\n2. Find the **Change Password** section\n3. Enter your **current password** to verify\n4. Enter and confirm your **new password**\n5. Click Save\n\n**Important:** Only the Super Admin can access the Settings page. Sub-admins cannot change the master password.\n\n⚠️ Use a strong password (12+ characters, mix of letters, numbers, symbols)."
    },
    {
        'keywords': ['ownership', 'transfer', 'transfer ownership', 'new admin', 'handover'],
        'response': "**Ownership Transfer** 🔄\n\nTo transfer admin ownership to someone else:\n1. Go to **Settings** → **Transfer Admin Ownership**\n2. Enter the new admin's **email address**\n3. Enter their **Telegram User ID** (they must give you this)\n4. Confirm with your **current password**\n5. Click Transfer\n\n**What happens:**\n• New admin gets a Telegram notification with a temporary password\n• You are automatically logged out\n• New admin becomes the Super Admin\n\n⚠️ This action is **irreversible** — make sure you trust the new admin."
    },
    {
        'keywords': ['team', 'sub admin', 'sub-admin', 'invite', 'role', 'roles', 'team admin', 'add admin', 'new team member'],
        'response': "**Team Admin Management** 👤\n\nYou can invite team members with specific roles:\n\n**Available Roles:**\n• **Transaction Manager** — Approve/reject orders\n• **Support Agent** — View orders & users (read-only)\n• **Giveaway Manager** — Manage giveaway claims\n• **Content Manager** — Send broadcast messages\n• **Email Manager** — Manage email subscribers\n• **Analyst** — View-only access to all data\n• **Moderator** — Transactions, giveaways, users\n\n**How to invite:**\n1. Settings → Team Admin Management\n2. Choose a role, enter their name\n3. Click **Generate Invite Link**\n4. Share the link — they set their own password\n5. They appear as **Pending** until they accept\n\nSub-admins **cannot** access Settings."
    },
    {
        'keywords': ['broadcast', 'message all', 'send message', 'bulk message', 'notify users', 'announcement'],
        'response': "**Broadcast Messages** 📢\n\nSend a message to **all** bot users at once:\n1. Go to **Broadcast** in the sidebar\n2. Type your message in the text box\n3. You can use **Telegram formatting**: *bold*, _italic_, `code`\n4. Click **Send Broadcast**\n5. The message is delivered to every user's Telegram inbox\n\n**Best practices:**\n• Keep messages concise and clear\n• Use broadcasts for: promotions, rate changes, downtime notices, giveaway announcements\n• Don't over-send — users can block the bot if spammed"
    },
    {
        'keywords': ['email', 'emails', 'email manager', 'subscribers', 'email blast', 'newsletter', 'email list'],
        'response': "**Email Management** 📧\n\nThe Emails section lets you manage your subscriber list and send email blasts.\n\n**What you can do:**\n• View all email subscribers collected by the bot\n• Send email announcements to all subscribers at once\n• Review the email send history (subject, date, recipients)\n\n**How to send an email blast:**\n1. Go to **Emails** in the sidebar\n2. Enter a subject line\n3. Write your email body (HTML supported)\n4. Click **Send to All**\n\nEmails are sent via the configured sender address in Settings."
    },
    {
        'keywords': ['logout', 'log out', 'sign out', 'session', 'exit'],
        'response': "**Logging Out** 🚪\n\nTo log out of the admin dashboard:\n• Click the **Logout** button in the top-right corner of the navigation bar\n• Your session is immediately invalidated\n• You'll be redirected to the login page\n\nSessions are secure and cookie-based. If you close the browser tab, you'll need to log in again next time (sessions don't persist indefinitely)."
    },
    {
        'keywords': ['permissions', 'access', 'what can', 'not access', 'restricted', 'permission denied'],
        'response': "**Access & Permissions** 🛡️\n\nAccess depends on your admin role:\n\n**Super Admin** — Full access to everything including Settings and team management\n\n**Sub-Admins** — Only see sections their role allows:\n• Transaction Manager → Dashboard + Transactions\n• Support Agent → Dashboard + Transactions (view) + Users\n• Analyst → Dashboard + all data (view-only)\n• Moderator → Dashboard + Transactions + Giveaway + Users\n\nIf you see a section is missing from your menu, your role doesn't have access to it. Ask the Super Admin to adjust your role or create a new invite with a different role."
    },
    {
        'keywords': ['search', 'find', 'filter', 'how to find', 'look for'],
        'response': "**Searching & Filtering** 🔍\n\nMost pages have a **real-time search bar** at the top:\n\n• **Transactions** — search by customer name, coin symbol, order type, or status\n• **Giveaway Claims** — search by LEEH code or username\n• **Users** — search by Telegram username or ID\n\nJust start typing — the table filters instantly, no need to press Enter.\n\n**Tips:**\n• Search is case-insensitive\n• Partial matches work (e.g. typing 'btc' finds all BTC orders)\n• Clear the search box to show all records again"
    },
    {
        'keywords': ['help', 'confused', 'what is', 'explain', 'how does', 'what does', 'guide', 'tutorial'],
        'response': "I'm here to help! 😊 Here are the main things I can explain:\n\n📊 **Dashboard** — overview of all stats\n💳 **Transactions** — how to approve, reject, bulk-manage orders\n🎁 **Giveaway** — managing promo code claims\n👥 **Users** — viewing bot user activity\n📈 **Crypto Rates** — live price feed\n⚙️ **Settings** — password, ownership, team management\n📢 **Broadcast** — messaging all users\n📧 **Emails** — email subscriber management\n\nJust ask me about any of these topics and I'll walk you through it!"
    },
]

def get_venora_mini_response(message: str) -> str:
    msg = message.lower().strip()
    best_score = 0
    best_response = None
    for topic in VENORA_MINI_KB:
        score = sum(1 for kw in topic['keywords'] if kw in msg)
        if score > best_score:
            best_score = score
            best_response = topic['response']
    if best_response and best_score > 0:
        return best_response
    # Fuzzy fallback — check partial word matches
    words = set(msg.split())
    for topic in VENORA_MINI_KB:
        for kw in topic['keywords']:
            kw_words = set(kw.split())
            if kw_words & words:
                return topic['response']
    return "I'm not sure about that specific question. Try asking about:\n\n• **Transactions** (approve, reject, bulk actions)\n• **Giveaway** claims and management\n• **Settings** (password, ownership transfer, team admins)\n• **Users**, **Crypto Rates**, **Broadcast**, or **Emails**\n\nOr describe what you're trying to do and I'll help point you in the right direction! 😊"

@app.route('/api/venora-mini', methods=['POST'])
@login_required
@super_admin_required
def venora_mini_chat():
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'No message provided'}), 400
    if len(message) > 500:
        message = message[:500]
    response = get_venora_mini_response(message)
    return jsonify({'response': response})

# ══════════════════════════════════════════════════════
#  API KEY SYSTEM v2 — PER-API-TYPE KEYS (NO EMAIL)
# ══════════════════════════════════════════════════════

VALID_API_TYPES = {
    'exchange': 'lx_ex_',
    'venora':   'lx_ai_',
    'bot':      'lx_bot_',
    'market':   'lx_mkt_',
    'webhook':  'lx_hook_',
    'auth':     'lx_auth_',
}

BROWSER_KEYS_FILE = 'browser_keys.json'

def load_browser_keys():
    if os.path.exists(BROWSER_KEYS_FILE):
        try:
            with open(BROWSER_KEYS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_browser_keys(data):
    try:
        with open(BROWSER_KEYS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving browser keys: {e}")

@app.route('/api/get-key/<api_type>', methods=['GET'])
def get_api_key_by_type(api_type):
    if api_type not in VALID_API_TYPES:
        return jsonify({'error': 'Invalid API type'}), 400
    browser_id = (request.args.get('bid') or '').strip()
    if not browser_id or len(browser_id) < 8 or len(browser_id) > 128:
        return jsonify({'error': 'Missing or invalid browser ID'}), 400
    keys = load_browser_keys()
    existing = next((k for k in keys if k.get('browser_id') == browser_id and k.get('api_type') == api_type), None)
    if existing:
        return jsonify({'key': existing['key'], 'api_type': api_type, 'existing': True})
    prefix = VALID_API_TYPES[api_type]
    new_key = prefix + secrets.token_hex(24)
    record = {
        'browser_id': browser_id,
        'api_type': api_type,
        'key': new_key,
        'created_at': datetime.now().isoformat()
    }
    keys.append(record)
    save_browser_keys(keys)
    return jsonify({'key': new_key, 'api_type': api_type, 'existing': False})


# ══════════════════════════════════════════════════════
#  VENORA FLASH — PUBLIC AI GUIDE (LANDING PAGE)
# ══════════════════════════════════════════════════════

VENORA_FLASH_KB = [
    {
        'keywords': ['hello', 'hi', 'hey', 'start', 'greet', 'yo', 'good morning', 'good afternoon'],
        'response': "Hey! 👋 I'm **Venora Flash** — your quick guide to LEEH Exchange.\n\nI can help you with:\n• What LEEH Exchange is and how it works\n• How to buy or sell crypto on the bot\n• Getting your free API key (no sign-up needed!)\n• Understanding our 6 APIs\n• Pricing and plans\n• Contacting customer support\n\nWhat would you like to know?"
    },
    {
        'keywords': ['what is leeh', 'about leeh', 'what is this', 'about this platform', 'leeh exchange', 'what do you do', 'platform'],
        'response': "**LEEH Exchange** 💱\n\nLEEH Exchange is a Nigerian crypto & gift card trading platform built into Telegram. You can:\n\n• **Buy crypto** — BTC, ETH, SOL, XRP, DOGE, TRX, BNB, POL, TON, SUI\n• **Sell crypto** — send coins, receive NGN to your Opay\n• **Sell gift cards** — Amazon, iTunes, Google Play, Steam, and more\n• **Buy airtime & data** — for all major Nigerian networks (MTN, Airtel, Glo, 9mobile)\n\nEverything happens through our **Telegram bot** — no apps to download, no accounts to create."
    },
    {
        'keywords': ['buy', 'buy crypto', 'how to buy', 'purchase', 'buying', 'buy bitcoin', 'buy btc', 'buy eth', 'buy sol'],
        'response': "**How to Buy Crypto** 🛒\n\n1. Open [@LEEHExchangeBot](https://t.me/LEEHExchangeBot) on Telegram\n2. Tap **💰 Buy Crypto**\n3. Select your coin (BTC, ETH, SOL, etc.)\n4. Enter the NGN amount you want to spend\n5. The bot locks in a **10-minute price quote**\n6. Pay NGN to our Opay account shown\n7. Upload your payment receipt in the bot\n8. Admin reviews & approves — you get a confirmation\n\n⏱️ Most orders approved within **5–30 minutes** during business hours."
    },
    {
        'keywords': ['sell', 'sell crypto', 'how to sell', 'selling', 'cash out', 'withdraw crypto'],
        'response': "**How to Sell Crypto** 💸\n\n1. Open [@LEEHExchangeBot](https://t.me/LEEHExchangeBot) on Telegram\n2. Tap **💸 Sell Crypto**\n3. Select which coin you're selling\n4. Enter the amount\n5. The bot gives you our wallet address & the NGN you'll receive\n6. Send your crypto to our wallet\n7. Paste your transaction hash in the bot\n8. Admin confirms receipt and sends NGN to your Opay\n\n🔒 Always double-check the wallet address before sending!"
    },
    {
        'keywords': ['api key', 'get key', 'free key', 'how to get key', 'api keys', 'copy key', 'get api', 'key for api'],
        'response': "**Getting Your Free API Key** 🔑\n\nNo sign-up or email needed — just visit the Developers page!\n\n**Steps:**\n1. Go to our [Developers page](/developers)\n2. Find the API you want to use\n3. Click **📋 Copy Key** on that card\n4. Your unique key is copied to clipboard instantly\n\n**Free plan rules:**\n• One copy per API type every **2 weeks**\n• Key is saved — it won't change if you come back\n• Store it safely in your `.env` file\n\nUse it with: `Authorization: Bearer YOUR_KEY`"
    },
    {
        'keywords': ['developer', 'developers', 'api', 'developer page', 'dev portal', 'build', 'integrate'],
        'response': "**Developer Platform** ⚡\n\nLEEH Exchange offers **6 production-ready APIs** for developers:\n\n1. **Core Exchange** — live crypto/NGN rates, order placement\n2. **Venora 1.0 AI** — AI chart signals (buy/sell/hold + confidence)\n3. **LEEH Bot API** — natural language crypto Q&A\n4. **Market Data** — OHLCV history, 1,000+ coins with NGN prices\n5. **Webhook** — real-time HTTP push for order & price events\n6. **Auth & Identity** — OAuth 2.0 key management\n\nVisit our [Developers page](/developers) for docs, code examples, and to get your free API keys!"
    },
    {
        'keywords': ['venora', 'venora ai', 'venora 1.0', 'ai model', 'chart analysis', 'trading signal', 'signal', 'analyze chart'],
        'response': "**Venora 1.0 — AI Trading Model** 🤖\n\nVenora is LEEH Exchange's proprietary AI trained on crypto chart data.\n\n**What it does:**\n• Detects **18 chart patterns** (Head & Shoulders, Flags, Wedges, Double Tops, Triangles, and more)\n• Returns **BUY / SELL / HOLD** signal with confidence score (0–100%)\n• Identifies support & resistance levels\n• Works on any coin, any timeframe (1m → 1W)\n\n**Use it via API:** POST to `/venora/v1/analyze` with your symbol and interval.\n\nGet a free Venora key at the [Developers page](/developers)."
    },
    {
        'keywords': ['pricing', 'price', 'plan', 'plans', 'free plan', 'pro plan', 'cost', 'how much', 'paid plan', 'upgrade', 'subscription'],
        'response': "**API Pricing** 💳\n\n**Starter (Free — Forever)**\n• 1,000 Core API requests/day\n• 100 Venora AI analyses/day\n• 500 Bot API queries/day\n• 2,000 Market Data requests/day\n• Unlimited Webhook events\n• No credit card required ✅\n\n**Pro — ₦15,000/month**\n• 50x higher limits across all APIs\n• 99.9% uptime SLA\n• Priority email support\n\n**Enterprise** — Custom pricing, dedicated infrastructure. [Contact us](https://t.me/LEEHExchangeBot)."
    },
    {
        'keywords': ['support', 'customer support', 'help me', 'contact', 'reach out', 'problem', 'issue', 'complaint', 'get help'],
        'response': "**Customer Support** 📞\n\nWe're here to help! Best ways to reach us:\n\n• **Telegram Bot** → open [@LEEHExchangeBot](https://t.me/LEEHExchangeBot) → use the Support option\n• **For transactions** → have your order ID ready (shown in bot confirmation)\n• **For API issues** → share your key prefix (e.g. `lx_ex_`) and the endpoint you're calling\n\n⏰ **Response times:**\n• Transactions: 5–30 min (business hours)\n• General: Within 2 hours\n• API support: Within 24 hours\n\nWe're an active Nigerian team — don't hesitate to reach out!"
    },
    {
        'keywords': ['coins', 'supported coins', 'cryptocurrencies', 'which coins', 'what coins', 'available coins', 'crypto list'],
        'response': "**Supported Cryptocurrencies** 🪙\n\nLEEH Exchange supports these coins for buying & selling:\n\n• Bitcoin (BTC) • Ethereum (ETH) • BNB (BNB)\n• Solana (SOL) • XRP (XRP) • Dogecoin (DOGE)\n• Tron (TRX) • Polygon (POL) • TON • Sui (SUI)\n\nLive NGN rates for all coins are shown in the [Markets section](#chart) of this page. Use the **Crypto Rates** API to get live prices programmatically."
    },
    {
        'keywords': ['payment', 'opay', 'bank', 'naira', 'ngn', 'how to pay', 'payment method', 'transfer'],
        'response': "**Payment Methods** 💰\n\n**Buying crypto:**\n• Transfer NGN to our **Opay** account (shown in the bot)\n• Upload your payment screenshot in the bot\n\n**Selling crypto:**\n• Send coins to our wallet address\n• Provide your Opay account in the bot\n• We send NGN within minutes of confirmation\n\n**Gift cards:**\n• Send card code via bot → NGN paid to your Opay\n\n✅ We use Opay for all NGN transfers — fast and instant."
    },
    {
        'keywords': ['gift card', 'gift cards', 'amazon', 'itunes', 'google play', 'steam', 'sell gift card', 'visa card'],
        'response': "**Gift Cards** 🎁\n\nWe buy a wide range of gift cards:\n• Amazon (US/UK) • iTunes / Apple • Google Play\n• Steam • Visa • eBay • Xbox • PlayStation & more\n\n**How to sell:**\n1. Bot → **🎁 Gift Cards**\n2. Select your brand and region\n3. Enter the card value → get a quote\n4. Submit the card code\n5. Receive NGN to your Opay within minutes ⚡"
    },
    {
        'keywords': ['airtime', 'data', 'data bundle', 'mtn', 'airtel', 'glo', '9mobile', 'recharge', 'top up', 'buy airtime'],
        'response': "**Airtime & Data** 📱\n\nBuy for all Nigerian networks: MTN, Airtel, Glo, 9mobile\n\n**Airtime:** Bot → 📱 Buy Airtime → pick network → enter number & amount\n**Data bundle:** Bot → 📶 Buy Data → pick network → choose plan → enter number\n\n⚡ Delivery is instant — arrives within seconds of payment!"
    },
    {
        'keywords': ['navigate', 'website', 'how to use site', 'pages', 'where is', 'navigation', 'find on site'],
        'response': "**Website Navigation** 🗺️\n\n**This landing page** — overview, live markets, features, FAQ\n**[Developers →](/developers)** — API docs, 6 free API keys, Venora AI spotlight, pricing\n**[Admin →](/admin)** — for the exchange team only\n\n**In the Telegram bot:**\n💰 Buy Crypto · 💸 Sell Crypto · 🎁 Gift Cards · 📱 Airtime & Data\n📊 My Orders · 💡 Check Rates · 🎟️ Giveaway / Points\n\nNeed something specific? Just ask me!"
    },
    {
        'keywords': ['help', 'what can you do', 'what do you know', 'guide', 'explain', 'tell me'],
        'response': "I'm **Venora Flash** ⚡ — your LEEH Exchange guide.\n\nI can answer questions about:\n\n🔑 **API keys** — how to get them (no sign-up!)\n⚡ **Our 6 APIs** — what each one does\n💰 **Buying / Selling** crypto on the bot\n🎁 **Gift cards & airtime** services\n💳 **Pricing** — free vs pro plans\n📞 **Customer support** — how to reach us\n🗺️ **Navigation** — finding things on the site\n\nJust ask and I'll guide you!"
    },
]

def get_venora_flash_response(message: str) -> str:
    msg = message.lower().strip()
    best_score = 0
    best_response = None
    for topic in VENORA_FLASH_KB:
        score = sum(1 for kw in topic['keywords'] if kw in msg)
        if score > best_score:
            best_score = score
            best_response = topic['response']
    if best_response and best_score > 0:
        return best_response
    words = set(msg.split())
    for topic in VENORA_FLASH_KB:
        for kw in topic['keywords']:
            if set(kw.split()) & words:
                return topic['response']
    return "I'm **Venora Flash** ⚡ — I can help with:\n\n• **What is LEEH Exchange** and how it works\n• **Buying/Selling** crypto, gift cards, airtime on the bot\n• **Getting API keys** (no sign-up needed)\n• **Our 6 APIs** and what they offer\n• **Pricing** — free vs pro\n• **Customer support** contact\n\nJust ask me anything about the platform! 😊"

@app.route('/api/venora-flash', methods=['POST'])
def venora_flash_chat():
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'No message provided'}), 400
    if len(message) > 500:
        message = message[:500]
    response = get_venora_flash_response(message)
    return jsonify({'response': response})


@app.route('/crypto-orders')
@login_required
@permission_required('transactions', 'transactions_view')
def crypto_orders_page():
    if not has_permission('transactions') and not has_permission('transactions_view'):
        return redirect(get_first_allowed_page(session.get('admin_permissions', [])))
    crypto_kw = ['btc','eth','bnb','sol','xrp','doge','trx','ton','sui','pol','usdt','crypto','coin']
    all_txs = load_transactions()
    orders = [t for t in all_txs if any(k in str(t.get('Type', '')).lower() for k in crypto_kw)]
    return render_template('crypto_orders.html', orders=orders)

@app.route('/gift-card-orders')
@login_required
@permission_required('giveaway', 'giveaway_view')
def gift_card_orders_page():
    if not has_permission('giveaway') and not has_permission('giveaway_view') and not has_permission('transactions'):
        return redirect(get_first_allowed_page(session.get('admin_permissions', [])))
    gift_kw = ['gift','amazon','itunes','google play','steam','ebay','paypal','visa','voucher','card']
    all_txs = load_transactions()
    orders = [t for t in all_txs if any(k in str(t.get('Type', '')).lower() for k in gift_kw)]
    claims = load_giveaway_claims()
    return render_template('gift_card_orders.html', orders=orders, claims=claims)

@app.route('/bank-withdrawals')
@login_required
@permission_required('transactions', 'transactions_view')
def bank_withdrawals_page():
    if not has_permission('transactions') and not has_permission('transactions_view'):
        return redirect(get_first_allowed_page(session.get('admin_permissions', [])))
    bank_kw = ['bank','withdraw','transfer','naira','ngn','opay','palmpay','fiat','cash']
    all_txs = load_transactions()
    orders = [t for t in all_txs if any(k in str(t.get('Type', '')).lower() for k in bank_kw)]
    return render_template('bank_withdrawals.html', orders=orders)

@app.route('/analytics')
@login_required
@permission_required('rates')
def analytics_page():
    from datetime import timedelta
    transactions = load_transactions()
    total_naira_num, total_usd_num = transaction_totals(transactions)
    pending_count = len([t for t in transactions if str(t.get('Status', 'Pending')).strip().lower() == 'pending'])
    completed_count = len([t for t in transactions if str(t.get('Status', '')).strip().lower() in ['approved', 'completed']])
    failed_count = len([t for t in transactions if str(t.get('Status', '')).strip().lower() in ['rejected', 'failed']])
    today = datetime.now().date()
    days30 = [(today - timedelta(days=i)) for i in range(29, -1, -1)]
    day_strs = [d.strftime('%Y-%m-%d') for d in days30]
    day_labels = [d.strftime('%b %d') for d in days30]
    day_counts = {d: 0 for d in day_strs}
    day_rev = {d: 0.0 for d in day_strs}
    type_counts: dict = {}
    for tx in transactions:
        ts = str(tx.get('Timestamp', ''))[:10]
        if ts in day_counts:
            day_counts[ts] += 1
            day_rev[ts] += transaction_revenue(tx)
        tx_type = tx.get('Type', 'Other')
        if tx_type and tx_type != 'User Join':
            type_counts[tx_type] = type_counts.get(tx_type, 0) + 1
    return render_template('analytics.html',
        total_revenue=format_naira_total(total_naira_num),
        total_naira=format_naira_total(total_naira_num),
        total_usd=format_usd_total(total_usd_num),
        combined_total=f"{total_naira_num + total_usd_num:,.2f}",
        total_transactions=len(transactions),
        pending_count=pending_count,
        completed_count=completed_count,
        failed_count=failed_count,
        chart_labels=day_labels,
        chart_counts=[day_counts[d] for d in day_strs],
        chart_revenue=[int(day_rev[d]) for d in day_strs],
        type_labels=list(type_counts.keys()),
        type_data=list(type_counts.values()),
    )

@app.route('/support-tickets')
@login_required
@super_admin_required
def support_tickets_page():
    if not session.get('is_super_admin'):
        return redirect(get_first_allowed_page(session.get('admin_permissions', [])))
    return render_template('support_tickets.html')

@app.route('/notifications')
@login_required
@super_admin_required
def notifications_page():
    if not session.get('is_super_admin'):
        return redirect(get_first_allowed_page(session.get('admin_permissions', [])))
    transactions = load_transactions()
    pending = [t for t in transactions if str(t.get('Status', 'Pending')).strip().lower() == 'pending']
    return render_template('notifications.html', pending_transactions=list(reversed(pending)))

@app.route('/telegram-bot-admin')
@login_required
@super_admin_required
def telegram_bot_admin_page():
    if not session.get('is_super_admin'):
        return redirect(get_first_allowed_page(session.get('admin_permissions', [])))
    transactions = load_transactions()
    user_count = len(set(str(t.get('UserID', t.get('Username', ''))) for t in transactions if t.get('UserID') or t.get('Username')))
    return render_template('telegram_bot_admin.html',
        bot_user_count=user_count,
        total_messages=len(transactions),
    )

# ─── Payment Config Management ──────────────────────────────────────────────
PAYMENT_CONFIG_FILE = 'payment_config.json'

def load_payment_config():
    if os.path.exists(PAYMENT_CONFIG_FILE):
        try:
            with open(PAYMENT_CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    # Fallback defaults
    try:
        import config as cfg
        wallets = getattr(cfg, 'WALLETS', {})
        return {
            "bank": {"bank_name": "Opay", "account_number": "8148842778", "account_name": "Abdulrofih Abdullah Hamzah"},
            "wallets": {k: v for k, v in wallets.items()}
        }
    except Exception:
        return {"bank": {"bank_name": "", "account_number": "", "account_name": ""}, "wallets": {}}

def save_payment_config(config):
    config['updated_at'] = datetime.now().isoformat()
    with open(PAYMENT_CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

@app.route('/payment-gateway')
@login_required
@super_admin_required
def payment_gateway_page():
    if not session.get('is_super_admin'):
        return redirect(get_first_allowed_page(session.get('admin_permissions', [])))
    config = load_payment_config()
    return render_template('payment_gateway.html', payment_config=config)

@app.route('/api/payment-config', methods=['GET'])
@login_required
def get_payment_config():
    if not session.get('is_super_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    return jsonify(load_payment_config())

@app.route('/api/payment-config/bank', methods=['POST'])
@login_required
def update_bank_config():
    if not session.get('is_super_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json(silent=True) or {}
    config = load_payment_config()
    config['bank'] = {
        'bank_name': data.get('bank_name', '').strip(),
        'account_number': data.get('account_number', '').strip(),
        'account_name': data.get('account_name', '').strip()
    }
    save_payment_config(config)
    return jsonify({'success': True, 'message': 'Bank details updated successfully'})

@app.route('/api/payment-config/wallet', methods=['POST'])
@login_required
def update_wallet_config():
    if not session.get('is_super_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json(silent=True) or {}
    coin = data.get('coin', '').strip().upper()
    address = data.get('address', '').strip()
    if not coin or not address:
        return jsonify({'error': 'Coin and address are required'}), 400
    config = load_payment_config()
    if 'wallets' not in config:
        config['wallets'] = {}
    config['wallets'][coin] = address
    save_payment_config(config)
    return jsonify({'success': True, 'message': f'{coin} wallet updated successfully'})

@app.route('/api/payment-config/wallet/delete', methods=['POST'])
@login_required
def delete_wallet_config():
    if not session.get('is_super_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json(silent=True) or {}
    coin = data.get('coin', '').strip().upper()
    if not coin:
        return jsonify({'error': 'Coin is required'}), 400
    config = load_payment_config()
    if coin in config.get('wallets', {}):
        del config['wallets'][coin]
        save_payment_config(config)
    return jsonify({'success': True, 'message': f'{coin} wallet removed'})

@app.route('/venora-mini-chat')
@login_required
@super_admin_required
def venora_mini_chat_page():
    return render_template('venora_mini_chat.html')

@app.route('/venora-flash-chat')
@login_required
@super_admin_required
def venora_flash_chat_page():
    return render_template('venora_flash_chat.html')

@app.route('/api/landing-stats')
def landing_stats():
    """Public endpoint — returns real platform statistics for the landing page."""
    try:
        transactions = load_transactions()
        total = len(transactions)
        completed = len([t for t in transactions if str(t.get('Status', '')).strip().lower() in ['approved', 'completed']])
        users = len(set(
            str(t.get('UserID') or t.get('Username') or '')
            for t in transactions
            if t.get('UserID') or t.get('Username')
        ))
        total_naira, total_usd = transaction_totals(transactions)
        crypto_volume = crypto_volume_breakdown(transactions)
        return jsonify({
            'total_trades': total,
            'completed_trades': completed,
            'active_users': max(users, 0),
            'trading_volume': int(total_naira),
            'trading_volume_ngn': round(total_naira, 2),
            'trading_volume_usd': round(total_usd, 2),
            'combined_value': round(total_naira + total_usd, 2),
            'crypto_volume': crypto_volume,
        })
    except Exception as e:
        return jsonify({
            'total_trades': 0,
            'completed_trades': 0,
            'active_users': 0,
            'trading_volume': 0,
            'trading_volume_ngn': 0,
            'trading_volume_usd': 0,
            'combined_value': 0,
            'crypto_volume': [],
        })


if __name__ == '__main__':
    print("🚀 Starting LEEH Exchange Admin Dashboard...")
    app.run(host='0.0.0.0', port=5000, debug=False)
