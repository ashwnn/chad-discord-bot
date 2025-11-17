## 1. Scope and goals

### 1.1 Product goals

* Provide a Discord bot that:

  * Responds to `!ask` using Grok chat completions.
  * Responds to `!image` using Grok image generation.
  * Uses a sarcastic, rude personality configured via a system prompt, without hate speech or explicit content.
  * Protects Grok credits via rate limits, token budgets, and spam filtering.
  * Supports an optional auto approve mode where admins must approve or override replies before they are sent.

* Provide an internal Web UI that:

  * Lets admins configure per guild limits and bot behavior.
  * Shows message history and usage analytics.
  * Exposes an approval queue for auto approve.
  * Allows admins to send manual replies instead of using Grok.
  * Follows the Tailscale login style system for look and feel. 

### 1.2 Out of scope

* Public user self service portal outside Discord.
* Non Discord chat platforms.
* Full role based access control beyond admin vs non admin.

---

## 2. Actors and use cases

### 2.1 Actors

* End user

  * Regular Discord member using `!ask` and `!image`.

* Guild admin

  * Discord server owner or moderator with access to the Web UI for that guild.
  * Can change limits, enable auto approve, approve or reject messages, and send manual replies.

* System

  * The bot plus Web UI backend that enforce rules, talk to Grok, and write to SQLite.

### 2.2 Primary use cases

1. User runs `!ask`

   * Bot validates input, checks limits.
   * If auto approve off, calls Grok and replies.
   * If auto approve on, queues for admin.

2. User runs `!image`

   * Similar to `!ask`, but uses image generation and image budgets.

3. Admin enables auto approve for a guild

   * All future non admin messages using `!ask` and `!image` get queued.

4. Admin reviews queue

   * Approves Grok generated answer, or
   * Writes a manual reply, or
   * Rejects the request.

5. Admin tunes limits and personality

   * Adjusts rate limits and daily budgets.
   * Edits system prompt per guild.

6. Admin reviews history and usage

   * Views per user usage, per guild usage, costs, and status for past requests.

---

## 3. High level architecture

### 3.1 Components

* Application backend (Python)

  * Discord adapter using `discord.py`.
  * HTTP Web UI backend (FastAPI or Flask).
  * Grok API client module.
  * Data access layer to SQLite.

* SQLite database

  * Shared between bot and Web UI.
  * Stores configuration, usage, message logs, and approval decisions.

* Grok API

  * Chat completions endpoint for `!ask`.
  * Image generation endpoint for `!image`.

### 3.2 Process model

Recommended deployment:

* Single Python application with:

  * Discord bot running in the main process.
  * Web server running in the same process or a sibling process, sharing the same SQLite file.
* Alternatively, two processes sharing a codebase and a database:

  * `bot` process: runs Discord loop and polls for admin actions.
  * `web` process: serves the Web UI and writes config and admin actions into SQLite.

The spec assumes both layers access a common abstraction over the database.

---

## 4. Functional requirements

### 4.1 Discord bot behavior

#### 4.1.1 Commands

* Command prefix: `!`

* `!ask <text>`

  * Required free text argument.
  * Bot responds with a text answer.
  * Personality defined by system prompt.
  * If auto approve is off:

    * Bot calls Grok directly and replies.
  * If auto approve is on:

    * Bot queues the message and optionally sends a “pending approval” notification.

* `!image <prompt>`

  * Required free text prompt.
  * Bot responds with an embedded image (first URL from Grok).
  * Same auto approve semantics as `!ask`.

* Non command messages

  * Ignored by the bot.

#### 4.1.2 Personality and system prompt

* Bot must always include a system message at the start of every Grok chat completion call.

* System prompt content:

  * Tone:

    * Sarcastic, blunt, occasionally rude.
    * May use mild profanity in short form.
  * Rules:

    * Always provide a correct and concise answer first.
    * Then optionally add a short sarcastic comment.
    * Never use slurs or target protected characteristics.
    * No explicit sexual content, no graphic violence.
    * Refuse disallowed content clearly and briefly.
  * Behavior on mistakes:

    * If question is unclear, spammy, or misuses commands, call it out in a sharp way but still explain what the user should do instead.

* The system prompt text must be configurable per guild via Web UI and stored in SQLite.

### 4.2 Input validation and spam filtering

For both `!ask` and `!image`:

* Empty or whitespace only input:

  * Reject with a sarcastic local reply.
  * Do not call Grok.

* Too short input (for example fewer than 5 characters):

  * Reject with a local reply such as “That barely qualifies as a question.”

* Known trivial strings (`hi`, `hello`, `test`, `ping`):

  * Reject with a local reply.
  * No Grok call.

* Gibberish:

  * Simple heuristic such as:

    * Very low variety of letters with repeated patterns.
  * Reject with a local reply.

* Excessive length:

  * Maximum characters per request (configurable, default 4000).
  * If exceeded, reject with a message asking user to shorten.

* Duplicate within short window:

  * If user sends identical content within a configurable window (default 60 seconds):

    * Reply locally that they already asked that.
    * No Grok call.

### 4.3 Rate limiting

Per guild configurable defaults:

* `!ask` per user:

  * Window size (seconds) and maximum calls per window.
  * Default: 5 calls per 60 seconds.

* `!image` per user:

  * Window size (seconds) and maximum calls per window.
  * Default: 3 calls per 300 seconds.

Behavior:

* If user exceeds the per user rate limit:

  * Reply with a local message indicating that they hit the spam limit.
  * Do not call Grok.

Limits are stored in the guild configuration table and enforced by the bot.

### 4.4 Credit protection and budgets

#### 4.4.1 Token budgets

Per guild, configurable:

* Per user daily chat token limit.
* Per guild daily chat token limit.

The bot must:

* Look up or create a row in the user daily usage table keyed by `(guild_id, user_id, day)` before every Grok chat call.
* Look up or create a row in global daily usage keyed by `(guild_id, day)`.
* If either limit is reached or exceeded:

  * Reply locally that the daily budget is used up.
  * Do not call Grok.

After each successful Grok chat call:

* Read `prompt_tokens`, `completion_tokens`, `total_tokens` from the Grok response usage section.
* Add `total_tokens` to the user daily row and guild daily row.
* Optionally compute an estimated dollar cost using configured price per million tokens and store it in the message log.

#### 4.4.2 Image budgets

Per guild, configurable:

* Per user daily image limit.
* Per guild daily image limit.

For every image request:

* Check and update user and guild image counts in daily usage tables.
* If limit reached:

  * Reply locally that image budget is exhausted.
  * Do not call Grok.

### 4.5 Grok chat integration

* Endpoint type

  * Use the OpenAI compatible style chat completion endpoint.
* Request construction

  * Model name: configurable, default to a Grok chat model.
  * Messages:

    * First element: system role, content from guild system prompt.
    * Second element: user role, content from the user prompt.
  * `max_tokens`: configured upper bound.
  * `temperature`: default moderate value (for example 0.5) configurable per guild.
* Response handling

  * Extract answer text from the first choice.
  * Extract usage object.
  * Persist request and response into the message log table including tokens used, cost, status.
  * Send the text back into Discord, formatted as a plain message or embed.

### 4.6 Grok image integration

* Endpoint type

  * Use the image generation endpoint with a Grok image model.

* Request construction

  * Model name: configurable, default to image capable Grok model.
  * Prompt: user provided prompt string.
  * `n`: number of images to generate per request (default 1).
  * `response_format`: URLs for simplicity.

* Response handling

  * Extract first image URL.
  * Persist URLs in `grok_image_urls` field in message log.
  * Send an embed in Discord with the URL set as image.
  * Update daily image usage counters.

### 4.7 Auto approve workflow

#### 4.7.1 Auto approve flag

* Each guild has a configuration flag `auto_approve_enabled`.
* When `true`, all non admin `!ask` and `!image` commands are queued for approval.
* Admins can bypass auto approve if desired, controlled by a separate `admin_bypass_auto_approve` flag.

#### 4.7.2 Pending message creation

When auto approve is enabled and an eligible user sends a valid command:

1. Bot enforces input validation and rate limits and daily budgets.
2. Instead of calling Grok:

   * Bot inserts a row into `message_log` with:

     * `status` set to `pending_approval`.
     * `needs_approval` set to true.
     * All basic metadata (guild, channel, user, content).
3. Bot optionally replies in the channel with a short message like:

   * “Your request is waiting for an admin to approve.”

No Grok cost is incurred at this time.

#### 4.7.3 Admin decisions

Via the Web UI, an admin can see all pending approval messages for their guild.

For each entry, admin can choose:

* Approve via Grok

  * Web UI sends an internal request to the backend instructing it to process the message using Grok.
  * Backend:

    * Reads the message record.
    * Calls Grok (chat or image).
    * Updates the message log with the Grok response, usage, and estimated cost.
    * Updates status to `approved_grok`, decision to `grok`, and records `approved_by_admin_id` and `approved_at`.
    * Sends the Grok reply to the original Discord channel, mentioning the user.

* Approve with manual reply

  * Web UI presents a text area for the admin to type their own reply.
  * On submit, backend:

    * Stores the manual reply text in `manual_reply_content`.
    * Sets status to `approved_manual`, decision to `manual`, and approval metadata.
    * Sends the manual reply to the original Discord channel.
    * Does not call Grok and does not increment token counters.

* Reject

  * Admin can optionally include a reason string.
  * Backend:

    * Sets status to `rejected`, decision to `reject`, records reason.
    * Sends a short rejection message in the original Discord channel, not including any sensitive details.

Auto approve applies to both `!ask` and `!image`. For `!image`, a manual approval might be a custom text reply or linking an image the admin chooses.

---

## 5. Non functional requirements

* Language

  * Python 3.10 or higher.

* Discord library

  * `discord.py` or equivalent maintained fork.

* Web framework

  * FastAPI or Flask.

* Database

  * SQLite with WAL mode enabled for concurrent access.

* Performance

  * Target response time:

    * For normal `!ask` and `!image` without auto approve: under a few seconds assuming Grok latency is normal.
  * Web UI pages should render within a second for typical data volumes.

* Reliability

  * Gracefully handle Grok HTTP errors and rate limits.
  * Use retries for transient network failures.
  * Avoid crashes on malformed data.

* Security

  * All secrets (Discord token, Grok API key) stored in environment variables or a secrets manager.
  * Web UI protected via authentication.
  * All admin actions authenticated and authorized.

---

## 6. Data model (SQLite)

Explain tables in terms of logical columns and constraints.

### 6.1 Table: `guild_config`

Purpose
Store per guild configuration including limits and persona.

Key columns

* `guild_id`

  * Primary key. Discord guild id.

* `auto_approve_enabled`

  * Boolean.

* `admin_bypass_auto_approve`

  * Boolean, default true.

* `ask_window_seconds`, `ask_max_per_window`

  * Integer.

* `image_window_seconds`, `image_max_per_window`

  * Integer.

* `user_daily_chat_token_limit`, `global_daily_chat_token_limit`

  * Integer.

* `user_daily_image_limit`, `global_daily_image_limit`

  * Integer.

* `system_prompt`

  * Text. Guild level persona.

* `temperature`, `max_completion_tokens`

  * Numeric settings for Grok chat.

* `created_at`, `updated_at`

  * Timestamps.

### 6.2 Table: `admin_users`

Purpose
Map Discord users to admin rights per guild.

Key columns

* `id`

  * Primary key.

* `discord_user_id`

  * Discord user id.

* `guild_id`

  * Guild id where they have admin rights.

* `role`

  * String label like `owner`, `admin`.

* `created_at`.

### 6.3 Table: `user_daily_usage`

Purpose
Track per user per day chat tokens and images.

Key columns

* `guild_id`, `user_id`, `day`

  * Composite primary key. `day` as `YYYY-MM-DD` in UTC.

* `chat_tokens_used`

  * Integer.

* `images_generated`

  * Integer.

* `last_updated`.

### 6.4 Table: `guild_daily_usage`

Purpose
Track per guild per day totals.

Key columns

* `guild_id`, `day`

  * Composite primary key.

* `chat_tokens_used`.

* `images_generated`.

* `last_updated`.

### 6.5 Table: `message_log`

Purpose
Record each handled command, its context, outcome, and cost.

Key columns

* `id`

  * Primary key.

* `guild_id`, `channel_id`, `user_id`, `discord_message_id`.

* `command_type`

  * `ask` or `image`.

* `user_content`

  * Text prompt.

* `grok_request_payload`

  * Optional JSON of what was sent to Grok for debugging.

* `grok_response_content`

  * Text answer for `!ask`.

* `grok_image_urls`

  * JSON array of URLs for `!image`.

* `prompt_tokens`, `completion_tokens`, `total_tokens`.

* `estimated_cost_usd`.

* `needs_approval`

  * Boolean.

* `status`

  * Enum text, possible values include:

    * `auto_responded`
    * `pending_approval`
    * `approved_grok`
    * `approved_manual`
    * `rejected`
    * `error`

* `decision`

  * `grok`, `manual`, `reject`, or null.

* `approved_by_admin_id`, `approved_at`.

* `manual_reply_content`.

* `error_code`, `error_detail`.

* `created_at`, `responded_at`.

### 6.6 Optional: `admin_actions`

If you prefer polling rather than internal HTTP calls, you can have a table for actions triggered by Web UI that the bot polls. Otherwise, you can embed the decision directly in `message_log` as described.

---

## 7. Web UI functional spec

### 7.1 Authentication and access control

* Web UI requires login.
* Recommended approach:

  * Discord OAuth for identity.
  * Map `discord_user_id` to `admin_users` table for authorization.
* If a logged in user is not in `admin_users` for any guild:

  * Show “no access” message.
* Each page is scoped to a single guild selected by the admin.

### 7.2 Navigation structure

Top level sections for a selected guild:

1. Overview (Dashboard)
2. Configuration
3. Approval queue
4. History
5. Analytics
6. Admin management (optional)

Navigation appears as a sidebar or top nav using the navigation link styles described in the style guide. 

### 7.3 Pages

#### 7.3.1 Overview (Dashboard)

Contents:

* Current bot state:

  * Auto approve status.
  * Whether bot is connected to Discord (optional if you expose it).
* Today’s usage (cards):

  * Chat tokens used vs limit.
  * Images generated vs limit.
* Key metrics:

  * Number of pending approvals.
  * Number of errors in last 24 hours.

Interactions:

* Toggle to enable or disable auto approve.
* Link to configuration and approval queue.

#### 7.3.2 Configuration page

Form grouped into cards:

* Rate limits:

  * Inputs for `ask_window_seconds`, `ask_max_per_window`.
  * Inputs for `image_window_seconds`, `image_max_per_window`.

* Budgets:

  * Inputs for per user and guild daily chat token limits.
  * Inputs for per user and guild daily image limits.

* Behavior:

  * Toggle for `admin_bypass_auto_approve`.
  * Dropdown for Grok chat model and image model names.
  * Input for default `max_completion_tokens` and `temperature`.

* Persona:

  * Text area for `system_prompt` with inline helper text reminding admin to avoid disallowed content.

Validation:

* All numeric fields must be non negative.
* Hard minimum for certain values (for example at least 1 request per window).
* On save:

  * Web UI sends updated values to backend.
  * Backend writes to `guild_config` and returns success or validation errors.

#### 7.3.3 Approval queue

List of all `message_log` entries with `status = 'pending_approval'` for the selected guild.

For each entry:

* Show:

  * Time created.
  * User and channel.
  * Command type (`ask` or `image`).
  * Short preview of prompt.

* Expand row to view details:

  * Full user content.
  * For `image`, show the prompt and optionally a preview if pre generated.

Actions:

* Approve via Grok:

  * For `ask`: triggers Grok chat call and sends reply to Discord.
  * For `image`: triggers Grok image generation and sends embed.
* Approve with manual reply:

  * Opens a dialog with a text area.
  * Backend records manual reply and sends it to Discord.
* Reject:

  * Optional text field for reason.
  * Backend updates status and sends rejection message.

Queue must auto refresh or support manual refresh.

#### 7.3.4 History

Table view with filters.

Filters:

* Date range.
* User id or user name.
* Command type.
* Status.
* Tokens used range.

Columns:

* Timestamp.
* User.
* Command type.
* Truncated prompt.
* Status.
* Tokens used (if chat).
* Decision (auto, Grok approved, manual, rejected).

Clicking a row opens a detail pane:

* Full user content.
* System prompt that was active at the time (if stored).
* Full Grok response or manual reply.
* Image URLs for image requests.
* Usage values and estimated cost.
* Any error codes.

#### 7.3.5 Analytics

Charts and summaries, for example:

* Line chart of daily chat tokens and images for last 30 days.
* Top N users by chat token consumption.
* Pie chart of approved vs rejected vs auto responded.

All analytics are derived from aggregations over `message_log` and usage tables.

---

## 8. Web UI visual and interaction style

The Web UI should visually match the login.tailscale.com design language. 

### 8.1 Layout and structure

* Use a centered content container with max width around 1120px for main content.
* Use responsive container breakpoints similar to:

  * 420px, 768px, 1024px for layout shifts.
* On desktop:

  * Sidebar navigation on the left using flex with vertical layout.
  * Content area on the right with cards for each section.
* On mobile:

  * Navigation collapses to a top navbar or hamburger.

Spacing:

* Base spacing unit 4px, mapped to increments as in the style guide.
* Use consistent vertical rhythm (for example 16px and 24px margins between sections). 

### 8.2 Color and theme

Adopt the semantic tokens from the style guide.

* Background:

  * `--color-bg-app` for main app background.
  * Cards use `--color-bg-base` with `--shadow-soft` or `--shadow-base` for elevation. 

* Text:

  * Primary text: `--color-text-base`.
  * Muted text (descriptions, metadata): `--color-text-muted`. 

* Primary accents:

  * Use blue scale for primary actions (`--color-blue-500` or `--color-blue-600`) for buttons and links. 

* Status colors:

  * Success: `--color-text-success`, `--color-green-200` backgrounds.
  * Warning: `--color-text-warning`, `--color-yellow-0` backgrounds.
  * Danger: `--color-text-danger`, `--color-red-0` backgrounds. 

* Borders:

  * Use `--color-border-interactive` for input borders and table boundaries.
  * Use `--color-border-focus` for focus outlines. 

Support dark mode:

* Use the same tokens with `html.dark` overrides so the UI automatically swaps to dark palette using the style system. 

### 8.3 Typography

* Base font family:

  * Inter as primary, with system sans fallbacks. 

* Font sizes:

  * Body text: `0.875rem`.
  * Section headings: `1.25rem` or `1.5rem` (text 2xl and 3xl).
  * Card titles and table headers: `1rem` to `1.125rem`. 

* Weights:

  * Body: normal (400).
  * Headings and important labels: semibold (600).
  * Primary navigation links and buttons: medium (500). 

* Letter spacing:

  * Use tight tracking for headings.
  * Uppercase table headers with wider tracking for better legibility. 

### 8.4 Components

#### 8.4.1 Buttons

* Base button:

  * Inline flex, center aligned.
  * Border radius `0.375rem` (rounded md).
  * Border width 1px.
  * Background: primary blue in normal state.
  * Text color: white.
  * Box shadow: `--shadow-button`. 

* Hover and active:

  * Slightly darker blue background.
  * Shadow increases to `--shadow-md` on hover. 

* Secondary buttons:

  * Background: `--color-bg-base`.
  * Border: `--color-border-interactive`.
  * Text: `--color-text-base`.

Use button groups where appropriate, such as in the approval queue for the three actions.

#### 8.4.2 Inputs and selects

* Height: around 2.25rem.

* Full width for configuration forms.

* Border radius: `0.375rem`.

* Border: `--color-border-interactive`.

* Background: `--color-bg-base`.

* Placeholder text: `--color-text-disabled`. 

* Focus:

  * Border color: `--color-border-focus`.
  * Outline with `--color-outline-focus`. 

* Error state:

  * Border and outline use the danger variants. 

#### 8.4.3 Toggles

* Use the `.toggle` pattern from the style guide:

  * Rounded full track with a pill shape.
  * White thumb that slides from left to right on active.
  * Off state track uses `--color-border-interactive`.
  * On state track uses `--color-blue-500`. 

Use toggles for:

* Auto approve enabled.
* Admin bypass auto approve.
* Dark mode if you expose it as a setting.

#### 8.4.4 Tables

* Use block style tables with flex rows as described in the style guide.

* Table headers:

  * Uppercase, small caps.
  * Muted text color.
  * Slightly increased letter spacing. 

* Rows:

  * Thin bottom border using `--color-border-base`.
  * Hover state can slightly change background to `--color-bg-menu-item-hover`. 

Use tables for:

* History lists.
* Analytics breakdowns.
* Admin lists.

#### 8.4.5 Tooltips and help

* Use small tooltip component for explaining advanced options:

  * Follows tooltip spec from style guide.
  * Background: soft gray.
  * Text: small with muted color. 

#### 8.4.6 Dialogs

* Approval dialog for manual replies:

  * Centered modal using `--shadow-dialog`.
  * Rounded border radius `0.375rem` or `0.5rem`.
  * Background `--color-bg-base`. 

### 8.5 Interactions and animations

* Use short transitions for hover and focus states:

  * Duration around 0.15 to 0.2 seconds.
  * Ease in out. 

* Do not over animate, but use:

  * Scale in for dropdowns or popovers.
  * Subtle shadow change on card hover if needed.

### 8.6 Accessibility

* Ensure all interactive components have clear focus outlines using the outline tokens.
* Use `sr-only` style for screen reader only labels where helpful.
* Support reduced motion preference by disabling non essential animations. 

---

## 9. Inter service contracts

You need clear contracts between Web UI frontend and backend, and between backend and Discord bot logic.

At a high level:

* Web UI frontend to backend:

  * REST endpoints for:

    * Reading and updating `guild_config`.
    * Listing pending messages and posting approval decisions.
    * Listing history and analytics aggregates.
    * Managing `admin_users`.

* Backend to Discord bot:

  * If they share process, backend directly calls bot functions to send messages.
  * If separate, use either:

    * Internal HTTP calls to a bot endpoint to process an approval, or
    * A DB based action queue that the bot polls.

Approval decision payloads include:

* `message_id`
* `decision` (`grok`, `manual`, `reject`)
* `manual_reply_content` (optional)

Bot must validate that the admin user has rights to the guild before acting.

---

## 10. Security and privacy

* Do not log the Grok API key or Discord token.
* Limit stored content:

  * `message_log` will store user prompts and responses; treat SQLite file as sensitive.
* Restrict Web UI to HTTPS behind authentication.
* Rate limit Web UI login attempts.
* Use CSRF protection on Web UI form submissions if applicable.

---

## 11. Testing checklist

* Unit tests:

  * Input validation and spam classification.
  * Rate limiting logic.
  * Daily budget enforcement.
  * Auto approve state transitions.

* Integration tests:

  * Full cycle `!ask` and `!image` in normal mode.
  * Auto approve workflow: pending to Grok approval, manual approval, rejection.
  * Web UI configuration updates reflected in bot behavior.

* UI tests:

  * Responsive design at breakpoints.
  * Dark mode compatibility.
  * Focus and keyboard navigation on all controls.