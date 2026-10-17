# LEEH Exchange Bot

## Overview

LEEH Exchange Bot is a comprehensive Telegram-based platform that enables users to buy and sell cryptocurrencies, buy and sell gift cards, purchase airtime, and buy data bundles. The bot provides real-time cryptocurrency pricing, telecom services integration, and seamless payment processing with complete order tracking capabilities. The admin dashboard features a premium, fully responsive web interface built with Tailwind CSS with advanced admin management including ownership transfer capabilities.

## System Architecture

The application follows a modular Python architecture with clear separation of concerns:

- **main.py**: Entry point and application orchestrator
- **config.py**: Configuration management and bot initialization
- **handlers.py**: Telegram message and command handlers
- **services.py**: Business logic and external API integration
- **utils.py**: Utility functions and helper methods
- **csv_handler.py**: Transaction logging and order history management
- **vtpass_service.py**: VTpass API integration for telecom services
- **app.py**: Flask web backend for admin dashboard

The bot uses a stateful conversation flow to guide users through buy/sell processes, maintaining user session data in memory. The admin dashboard provides real-time transaction monitoring, giveaway management, user activity tracking, cryptocurrency rate monitoring, and secure admin credential management with ownership transfer.

## Key Components

### Bot Framework
- **Technology**: Python Telebot library
- **Purpose**: Handles Telegram Bot API interactions
- **Rationale**: Provides robust, well-documented interface for Telegram bots with built-in polling and webhook support

### Admin Dashboard (Web Interface)
- **Framework**: Flask with Jinja2 templates + Tailwind CSS
- **Styling**: Premium blue and white design system with utility-first CSS
- **Design**: Fully responsive, mobile-first, accessible across all devices
- **Features**: 
  - Dashboard with real-time stats
  - Transaction monitoring and bulk actions
  - Giveaway claim management
  - User activity tracking
  - Live cryptocurrency rates from CoinGecko API
  - Admin settings (password change, ownership transfer)
  - Admin ID management with email verification

### Configuration Management
- **Approach**: Environment variables with fallback defaults
- **Security**: Sensitive data (admin IDs) sourced from environment
- **Wallet Integration**: Pre-configured cryptocurrency wallet addresses for multiple chains
- **Bot Token**: Kept completely hidden from dashboard UI

### State Management
- **Implementation**: In-memory user state storage
- **Trade-off**: Simple but not persistent across restarts
- **Alternative Considered**: Database storage (could be added for production scalability)

### Price Feed Integration
- **Provider**: CoinGecko API
- **Rationale**: Free, reliable, and comprehensive cryptocurrency price data
- **Error Handling**: Graceful fallback to "N/A" when API fails
- **Dashboard Display**: Live rates displayed in Crypto Rates section with auto-refresh every 60 seconds

## Data Flow

1. **User Interaction**: Users interact via Telegram commands and buttons
2. **State Tracking**: Bot maintains conversation state to track user progress
3. **Price Fetching**: Real-time price data retrieved from CoinGecko API
4. **Payment Processing**: Users directed to appropriate payment methods (crypto wallets or bank details)
5. **Order Management**: Transaction details formatted and presented to users
6. **Admin Dashboard**: Admin views real-time transaction data, manages orders, tracks giveaway claims, monitors users
7. **User Activity**: All user interactions logged to CSV for admin review

## External Dependencies

### APIs
- **Telegram Bot API**: Core bot functionality
- **CoinGecko API**: Cryptocurrency price data
- **Rate Limiting**: Built-in request timeouts and error handling

### Payment Infrastructure
- **Cryptocurrency Wallets**: Multi-chain wallet addresses for receiving payments
- **Banking**: Opay bank integration for fiat transactions
- **Security**: Read-only wallet addresses minimize security risk

### Frontend Technologies
- **Tailwind CSS**: Utility-first CSS framework for responsive design
- **JavaScript**: Lightweight interactions for modals, search, and bulk actions
- **Responsive Design**: Mobile-first approach with Tailwind breakpoints (sm, md, lg, xl)

## Deployment Strategy

### Environment Setup
- **Python Requirements**: telebot, requests, logging, flask, flask-cors, pandas
- **Configuration**: Environment variables for sensitive data
- **Logging**: Structured logging with configurable levels

### Runtime Considerations
- **Polling**: Uses infinity polling for real-time message processing
- **Error Recovery**: Graceful error handling with user-friendly messages
- **Scalability**: Single-instance design suitable for moderate traffic
- **Web Server**: Flask application serves admin dashboard on port 5000

## Dashboard Routes & Features

### Pages
1. **Login** (`/login`): Secure authentication with premium UI
2. **Dashboard** (`/dashboard`): Stats grid, recent transactions, giveaway activity
3. **Transactions** (`/transactions`): Full transaction ledger with search, bulk actions, status management
4. **Giveaway Claims** (`/giveaway-claims`): Searchable giveaway claims table with verification status
5. **Users** (`/users`): All bot users with activity metrics
6. **Crypto Rates** (`/crypto-rates`): Live crypto prices from CoinGecko with auto-refresh
7. **Settings** (`/settings`): Admin password management, ownership transfer, system info

### API Endpoints
- `GET /api/transactions` - Fetch all transactions
- `GET /api/giveaway-claims` - Fetch all giveaway claims
- `GET /api/stats` - Get dashboard statistics
- `GET /api/crypto-rates` - Fetch live cryptocurrency rates
- `POST /api/change-password` - Change admin password
- `POST /api/transfer-ownership` - Transfer admin ownership to new admin with email
- `POST /api/transaction/approve` - Approve single transaction
- `POST /api/transaction/reject` - Reject single transaction
- `POST /api/transaction/pending` - Set transaction to pending
- `POST /api/transaction/bulk-approve` - Bulk approve transactions
- `POST /api/transaction/bulk-reject` - Bulk reject transactions
- `POST /api/transaction/bulk-pending` - Bulk set to pending

## UI/UX Design System

### Premium Design
- **Color Palette**: Professional blue (#0052FF) with white, success, danger, warning accents
- **Typography**: Neue Machina (headings), Inter (body) - premium fintech aesthetic
- **Components**: Cards with subtle shadows, smooth transitions, hover effects
- **Responsiveness**: Fully responsive sm/md/lg/xl breakpoints

### Interactive Elements
- **Mobile Menu**: Hidden desktop nav, toggle menu for mobile
- **Search Filtering**: Live search on tables with instant results
- **Bulk Actions**: Smart toolbar that appears when items selected
- **Modals**: Smooth backdrop blur with transitions
- **Forms**: Accessible inputs with focus states and validation

## Multi-Admin System (Role-Based Access Control)

### How It Works
1. Super admin goes to Settings → Team Admin Management
2. Picks a role from the 7 available roles
3. Enters the new admin's name and clicks "Generate Invite Link"
4. Shares the link (e.g. `https://domain/admin-invite/<token>`) with the team member
5. Team member opens the link, sets their own username and password
6. Their account activates and they can log in immediately — with only the sections their role allows

### Available Roles
| Role | Sections Accessible |
|------|-------------------|
| Transaction Manager | Dashboard, Transactions (approve/reject) |
| Support Agent | Dashboard, Transactions (view only), Users |
| Email Manager | Dashboard, Emails |
| Giveaway Manager | Dashboard, Giveaway |
| Content Manager | Dashboard, Broadcast |
| Analyst | Dashboard, Transactions (view), Users, Rates, Giveaway (view) |
| Moderator | Dashboard, Transactions, Giveaway, Users |

### Security
- Super admin password required to create invites
- Invite tokens are single-use — expire once accepted
- Sub-admins cannot access Settings (super admin only)
- Pending admins shown with a "Regenerate Link" button to resend fresh link
- Any sub-admin can be removed instantly from Settings

### Data Storage
- Sub-admins stored in `admin_config.json` under `sub_admins` list
- Each entry has: id, name, role, permissions, invite_token, status, username, login_email, password, created_at, activated_at

## Admin Ownership Transfer

### How It Works
1. Current admin goes to Settings → Transfer Admin Ownership
2. Enters new admin's email address and Telegram User ID
3. Confirms transfer with current password
4. New admin receives Telegram notification with temporary password
5. Current admin is logged out
6. New admin can now manage the dashboard

### Security
- Requires current admin password verification
- Email address stored for reference
- New admin ID must be valid Telegram user ID
- Telegram notification sent to confirm transfer

## Developer Portal (API System)

### API Key System
- Free tier: enter email → get `lx_free_` + 40-char hex key instantly
- Keys stored in `api_keys.json` (email, key, tier, created_at, last_copied)
- Copy rate limit: once per 7 days per email, tracked server-side
- Routes: `POST /api/generate-key`, `POST /api/copy-key`
- No Telegram redirect — everything handled in-browser on /developers

### Venora Mini (In-Dashboard AI)
- Floating button (bottom-right of every admin page) with purple/blue gradient
- Slide-in chat panel with full message history, typing indicator, quick suggestions
- Knowledge base covers: dashboard, transactions, approve/reject, bulk actions, giveaway, users, crypto rates, settings, password, ownership transfer, team admins, roles, broadcast, emails, logout, permissions, search
- Route: `POST /api/venora-mini` (login_required)
- Pure rule-based keyword matching — no external API

## Changelog

- July 01, 2025. Initial setup
- July 01, 2025. Upgraded bot implementation with enhanced features
- July 01, 2025. Added comprehensive order tracking system
- July 01, 2025. Integrated telecom services with VTpass API
- July 01, 2025. Migrated to python-telegram-bot library
- December 23, 2025. Applied premium blue and white design theme to web interface
- December 23, 2025. Implemented comprehensive Tailwind CSS responsive design system
- December 23, 2025. Enhanced all pages with premium fintech aesthetic and mobile-first approach
- December 24, 2025. Added Users page showing all bot users with activity metrics
- December 24, 2025. Added Crypto Rates page with live CoinGecko API integration
- December 24, 2025. Added Settings page with admin password management and system info
- December 24, 2025. Added admin ownership transfer via email with new admin ID assignment
- December 24, 2025. Removed all bot token references from dashboard UI for security

## User Preferences

Preferred communication style: Simple, everyday language.

## Technical Notes

### Supported Cryptocurrencies
- Bitcoin (BTC), Ethereum (ETH), Polygon (POL), Binance Coin (BNB)
- Solana (SOL), XRP, Dogecoin (DOGE), Tron (TRX)
- TON, Sui (SUI)

### Architecture Decisions

**Stateful Conversations**: Chosen over stateless interactions to provide guided user experience through complex buy/sell flows. In-memory storage keeps implementation simple but requires consideration for production deployment.

**Modular Design**: Separation of handlers, services, and utilities enables maintainability and testing. Each module has a clear responsibility boundary.

**Error Resilience**: Comprehensive error handling ensures bot remains responsive even when external services (price APIs, payment systems) experience issues.

**Multi-Currency Support**: Flexible wallet and pricing configuration supports easy addition of new cryptocurrencies without code changes.

**Tailwind CSS for UI**: Chosen for responsive design, utility-first approach, and minimal CSS footprint. Enables rapid responsive development without custom CSS overhead.

**Lightweight JavaScript**: Minimal JS for interactivity - modals, search, bulk actions, no heavy frameworks for fast page load and smooth interactions.

**CoinGecko API Integration**: Free, reliable cryptocurrency price data with no authentication required. Auto-refresh every 60 seconds for live rates on dashboard.

**Admin Ownership Transfer**: Email-based verification ensures secure handoff of admin control. New admin ID replaces old admin ID globally, ensuring seamless transition.
