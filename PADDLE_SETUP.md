# Paddle Integration Guide for Chess Analyzer

This guide explains how to integrate Paddle (v2) payments into your Chess Analyzer application using Streamlit (Frontend) and Supabase (Backend).

## 1. Prerequisites
- A **Paddle** account (Sandbox for testing).
- A **Supabase** project.
- Use `src/paddle_integration.py` (already created).

## 2. Database Setup (Supabase)

Run this SQL in your Supabase SQL Editor to create tables for subscriptions and puzzle solution caching.

```sql
-- Subscriptions table for Paddle
create table if not exists subscriptions (
  subscription_id text primary key,
  user_email text not null,
  status text not null, -- 'active', 'past_due', 'canceled'
  plan_id text,
  created_at timestamp with time zone default timezone('utc'::text, now()),
  updated_at timestamp with time zone default timezone('utc'::text, now())
);

-- Optional: Enable RLS so users can only read their own sub
alter table subscriptions enable row level security;

create policy "Users can read own subscription"
  on subscriptions for select
  using ( auth.email() = user_email );

-- Puzzle Solutions Cache (speeds up "other users" puzzles)
create table if not exists puzzle_solutions (
  puzzle_key text primary key,
  solution_line jsonb not null, -- Array of UCI moves, e.g. ["e2e4", "e7e5", "g1f3"]
  created_at timestamp with time zone default timezone('utc'::text, now())
);

-- Index for fast lookups
create index if not exists idx_puzzle_solutions_key on puzzle_solutions(puzzle_key);
```

## 3. Backend: Webhook Handler (Supabase Edge Function)

Since Streamlit cannot easily host a secure webhook endpoint, use a **Supabase Edge Function**.

1. Create a function: `supabase functions new paddle-webhook`
2. specific code for `index.ts`:

```typescript
// supabase/functions/paddle-webhook/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from "https://esm.sh/@supabase/supabase-js@2"

// Verify webhook signature (Simplest method: check secret in query param or header if Paddle allows, 
// strictly you should verify Paddle signature using crypto. For MVP, use a shared secret.)
const WEBHOOK_SECRET = Deno.env.get('PADDLE_WEBHOOK_SECRET')

serve(async (req) => {
  const supabase = createClient(
    Deno.env.get('SUPABASE_URL') ?? '',
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
  )

  const signature = req.headers.get('paddle-signature')
  // TODO: Add strict signature verification here using paddle-sdk if available or crypto
  
  const body = await req.json()
  const eventType = body.event_type # e.g. "subscription.created", "transaction.completed"
  const data = body.data

  console.log(`Received event: ${eventType}`)

  if (eventType === 'subscription.created' || eventType === 'subscription.updated') {
     const subId = data.id
     const status = data.status
     const email = data.custom_data?.email || data.user?.email // Depends on how you pass email
     const items = data.items 
     const priceId = items[0]?.price?.id

     if (email) {
        const { error } = await supabase
          .from('subscriptions')
          .upsert({ 
            subscription_id: subId,
            user_email: email,
            status: status,
            plan_id: priceId,
            updated_at: new Date().toISOString()
          })
        
        if (error) console.error('Error updating DB:', error)
     }
  }

  return new Response(JSON.stringify({ received: true }), {
    headers: { "Content-Type": "application/json" },
  })
})
```

3. Deploy: `supabase functions deploy paddle-webhook`
4. Add the URL (e.g., `https://<ref>.functions.supabase.co/paddle-webhook`) to your Paddle Webhook settings.

## 4. Frontend Integration (Streamlit)

Use the helper helper file `src/paddle_integration.py`.

### Step 1: Initialize
In `streamlit_app.py` (or `app.py`):

```python
from src.paddle_integration import init_paddle, render_checkout_button

# Initialize at the top of your UI
init_paddle() 
```

### Step 2: Create a "Go Premium" Section

```python
st.header("Upgrade to Pro")
st.write("Unlock advanced analytics and AI coaching.")

# Replace with your actual Price ID from Paddle Dashboard
PRICE_ID = "pri_0123456789" 

# Use user's email if logged in
user_email = st.session_state.get("user_email", None)

render_checkout_button(
    price_id=PRICE_ID,
    customer_email=user_email,
    button_text="Subscribe - $9.99/mo"
)
```

## 5. Verification (Gating Features)

In your python code, check the subscription status before showing features.

```python
from puzzles.supabase_client import supabase

def is_user_premium(email: str) -> bool:
    if not email:
        return False
    
    # Check if they have an active subscription
    response = supabase.table("subscriptions")\
        .select("status")\
        .eq("user_email", email)\
        .in_("status", ["active", "trialing"])\
        .execute()
        
    return len(response.data) > 0

# Usage
if is_user_premium("user@example.com"):
    show_advanced_stats()
else:
    st.info("🔒 This feature is locked. Upgrade to access.")
```
