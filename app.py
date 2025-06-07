import streamlit as st
import openai
import sqlite3
import json
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

# --- Page Configuration ---
st.set_page_config(
    page_title="Event Marketing Assistant",
    page_icon="✨",
    layout="wide"
)

# --- OpenAI API Setup ---
# Load environment variables
load_dotenv(override=True)
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Database Configuration
DB_FILE=os.getenv("DB_FILE", "events.db")

# It's recommended to set the API key as an environment variable.
# However, for this app, we'll use the sidebar input for ease of use.
st.sidebar.title("Configuration")
OPENAI_API_KEY = st.sidebar.text_input("Enter your OpenAI API Key", type="password")
if not OPENAI_API_KEY:
    st.warning("Please enter your OpenAI API Key in the sidebar to begin.")
    st.stop()
else:
    client = openai.OpenAI(api_key=OPENAI_API_KEY)

# --- Database Setup ---
def initialize_database():
    """Initializes the SQLite database and creates the events table if it doesn't exist."""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                start_time TEXT,
                end_time TEXT,
                location TEXT,
                facilitators TEXT,
                description TEXT,
                fb_image_url TEXT,
                ig_image_url TEXT,
                newsletter_html TEXT,
                created_at TEXT
            )
        ''')
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        st.error(f"Database error: {e}")

# --- Session State Initialization ---
def init_session_state():
    """Initializes session state variables to manage the workflow."""
    if 'stage' not in st.session_state:
        st.session_state.stage = 'initial'
    if 'description_approved' not in st.session_state:
        st.session_state.description_approved = False
    if 'fb_image_approved' not in st.session_state:
        st.session_state.fb_image_approved = False
    if 'ig_image_approved' not in st.session_state:
        st.session_state.ig_image_approved = False
    if 'newsletter_approved' not in st.session_state:
        st.session_state.newsletter_approved = False
    if 'generated_description' not in st.session_state:
        st.session_state.generated_description = ""
    if 'fb_image_url' not in st.session_state:
        st.session_state.fb_image_url = None
    if 'ig_image_url' not in st.session_state:
        st.session_state.ig_image_url = None
    if 'newsletter_html' not in st.session_state:
        st.session_state.newsletter_html = ""
    if 'user_inputs' not in st.session_state:
        st.session_state.user_inputs = {}


# --- AI Agent Functions ---

def run_content_writer_agent(title, start_time, end_time, location, facilitators, short_desc):
    """Agent 1: Generates the detailed event description."""
    st.info("🤖 Agent 1 (Content Writer) is drafting the event description...")
    prompt = f"""
    You are an expert marketing copywriter for wellness and spiritual events.
    Your task is to write a detailed, engaging, and inspiring event description of approximately 10 sentences.
    The tone should be welcoming, warm, and vibrant.

    Use the following event details to craft your description:
    - Event Title: {title}
    - Facilitators: {facilitators}
    - Event Type Hint: The title suggests it's a {title.lower()} event.

    Base your description on these details.
    """
    if short_desc:
        prompt += f"\nPlease also incorporate the following user-provided details or themes: '{short_desc}'"

    try:
        # Note: Using Chat Completions API as it's efficient for this single-turn task.
        # The Assistants API is better for multi-turn conversational agents.
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert marketing copywriter for wellness events."},
                {"role": "user", "content": prompt}
            ]
        )
        generated_text = response.choices[0].message.content

        # Format the final output
        formatted_description = (
            f"{generated_text}\n\n"
            f"**Facilitators:** {facilitators}\n\n"
            f"**When:** {start_time.strftime('%A, %B %d, %Y at %I:%M %p')} to {end_time.strftime('%I:%M %p')}\n\n"
            f"**Where:** {location}"
        )
        st.session_state.generated_description = formatted_description
        st.success("🤖 Agent 1 finished writing!")
    except openai.APIError as e:
        st.error(f"OpenAI API Error: {e}. The service might be down. Please try again later.")
    except (openai.RateLimitError, openai.AuthenticationError) as e:
        st.error(f"OpenAI API Error: {e}. Please check your API key or usage limits.")
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")


def run_image_designer_agent(title, description, size, agent_name):
    """Agent 2 & 3: Generates an image using DALL-E 3."""
    st.info(f"🤖 {agent_name} is designing the image...")
    prompt = f"""
    Create a visually stunning, high-quality image for a wellness event titled "{title}".
    The image must have the exact text "{title}" clearly visible and legible on it.
    The aesthetic should be inspiring, serene, and suitable for a spiritual/wellness event (like ecstatic dance, yoga, or meditation).
    The image should be vibrant and professional.
    Key themes from the event description: {description[:500]}
    """
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            n=1,
            size=size, # "1792x1024" for FB, "1024x1024" for IG
            quality="hd",
        )
        image_url = response.data[0].url
        st.success(f"🤖 {agent_name} finished designing!")
        return image_url
    except openai.APIError as e:
        st.error(f"DALL-E Error: {e}. The service might be having issues. Please try again.")
    except Exception as e:
        st.error(f"An unexpected error occurred during image generation: {e}")
        return None


def run_newsletter_composer_agent(title, description, image_url):
    """Agent 4: Generates an HTML newsletter."""
    st.info("🤖 Agent 4 (Newsletter Composer) is drafting the email...")
    prompt = f"""
    You are an expert email marketer. Create a complete, well-formatted HTML newsletter for a wellness event.
    Use the following materials:
    - Event Title: {title}
    - Header Image URL: {image_url}
    - Full Event Description (use this exact text): {description}

    The HTML should be visually appealing, with a clean layout.
    - Use the image as a header banner.
    - The text should be with black font on white background.
    - Use the event title as a main heading (<h1>).
    - Include the full description text.
    - The HTML should be self-contained and ready to be sent.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert email marketer specializing in HTML emails."},
                {"role": "user", "content": prompt}
            ]
        )
        html_content = response.choices[0].message.content
        # Clean up the response to get only the HTML
        if "```html" in html_content:
            html_content = html_content.split("```html")[1].split("```")[0]
        st.session_state.newsletter_html = html_content.strip()
        st.success("🤖 Agent 4 finished composing!")
    except Exception as e:
        st.error(f"An unexpected error occurred during newsletter generation: {e}")


# --- Helper Functions ---

def save_event_to_db():
    """Saves the final, approved event details to the SQLite database."""
    try:
        conn = sqlite3.connect('events.db')
        c = conn.cursor()
        c.execute('''
            INSERT INTO events (title, start_time, end_time, location, facilitators, description, fb_image_url, ig_image_url, newsletter_html, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            st.session_state.user_inputs.get('title'),
            st.session_state.user_inputs.get('start_time').isoformat(),
            st.session_state.user_inputs.get('end_time').isoformat(),
            st.session_state.user_inputs.get('location'),
            st.session_state.user_inputs.get('facilitators'),
            st.session_state.generated_description,
            st.session_state.fb_image_url,
            st.session_state.ig_image_url,
            st.session_state.newsletter_html,
            datetime.datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()
        st.success("🎉 Event successfully saved to the database!")
    except sqlite3.Error as e:
        st.error(f"Database Save Error: {e}")


def send_gmail(sender_email, app_password, recipient_email, subject, html_body):
    """Sends an email using a Gmail account."""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg.attach(MIMEText(html_body, 'html'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, app_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        st.success(f"✅ Test email successfully sent to {recipient_email}!")
    except smtplib.SMTPAuthenticationError:
        st.error("Authentication failed. Please check your sender email and Google App Password.")
    except Exception as e:
        st.error(f"Failed to send email: {e}")


# --- Main Application UI ---

def create_event_page():
    st.header("1. Enter Event Details")

    with st.form("event_form"):
        title = st.text_input("Event Title", "Ecstatic Dance - Flight - The Art Of Being Free")
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date", datetime.date.today())
        with col2:
            start_time_val = st.time_input("Start Time", datetime.time(19, 0))
        col3, col4 = st.columns(2)
        with col3:
            end_date = st.date_input("End Date", datetime.date.today())
        with col4:
            end_time_val = st.time_input("End Time", datetime.time(21, 0))

        location = st.text_input("Location", "Prostranstvoto, Sheinovo 7, Sofia, Bulgaria")
        facilitators = st.text_input("Facilitators' Names (comma-separated)", "Man Of No Ego, Devi Flow")
        short_desc = st.text_area("Short Description / Key Themes (Optional)",
                                  "Being free is an art. Get into your body, clean your mind and enjoy the Art of Living.")

        st.header("2. Select Content to Generate")
        gen_fb = st.checkbox("Generate Facebook Content (Description + Image)", True)
        gen_ig = st.checkbox("Generate Instagram Content (Description + Image)", True)
        gen_news = st.checkbox("Generate Newsletter Email", True)

        submitted = st.form_submit_button("✨ Generate Content ✨", type="primary")

    # Input Validation
    start_datetime = datetime.datetime.combine(start_date, start_time_val)
    end_datetime = datetime.datetime.combine(end_date, end_time_val)
    if start_datetime >= end_datetime:
        st.warning("Warning: The event's start time is after or the same as its end time.")

    if submitted:
        # Reset state for a new generation
        for key in ['stage', 'description_approved', 'fb_image_approved', 'ig_image_approved', 'newsletter_approved',
                    'generated_description', 'fb_image_url', 'ig_image_url', 'newsletter_html']:
            if key in st.session_state:
                del st.session_state[key]
        init_session_state()

        st.session_state.user_inputs = {
            'title': title, 'start_time': start_datetime, 'end_time': end_datetime,
            'location': location, 'facilitators': facilitators, 'short_desc': short_desc,
            'gen_fb': gen_fb, 'gen_ig': gen_ig, 'gen_news': gen_news
        }
        st.session_state.stage = 'generate_description'
        st.rerun()

    # --- Agent 1: Content Writer ---
    if st.session_state.stage == 'generate_description':
        with st.spinner("Thinking..."):
            run_content_writer_agent(
                st.session_state.user_inputs['title'],
                st.session_state.user_inputs['start_time'],
                st.session_state.user_inputs['end_time'],
                st.session_state.user_inputs['location'],
                st.session_state.user_inputs['facilitators'],
                st.session_state.user_inputs['short_desc']
            )
        st.session_state.stage = 'review_description'
        st.rerun()

    if st.session_state.stage in ['review_description', 'Image Generations', 'review_images', 'generate_newsletter', 'review_newsletter', 'final']:
        st.markdown("---")
        st.header("Agent 1: Content Writer Output")
        edited_description = st.text_area("You can edit the generated description below:",
                                          value=st.session_state.generated_description, height=300)
        st.session_state.generated_description = edited_description # Persist edits

        if not st.session_state.description_approved:
            if st.button("Approve Description", type="primary"):
                st.session_state.description_approved = True
                st.session_state.stage = 'Image Generations'
                st.rerun()

    # --- Agent 2 & 3: Image Designers ---
    if st.session_state.stage == 'Image Generations' and st.session_state.description_approved:
        with st.spinner("Designing visuals..."):
            if st.session_state.user_inputs['gen_fb'] and not st.session_state.fb_image_approved:
                st.session_state.fb_image_url = run_image_designer_agent(
                    st.session_state.user_inputs['title'],
                    st.session_state.generated_description,
                    "1792x1024",
                    "Facebook Designer"
                )
            if st.session_state.user_inputs['gen_ig'] and not st.session_state.ig_image_approved:
                st.session_state.ig_image_url = run_image_designer_agent(
                    st.session_state.user_inputs['title'],
                    st.session_state.generated_description,
                    "1024x1024",
                    "Instagram Designer"
                )
        st.session_state.stage = 'review_images'
        st.rerun()

    if st.session_state.stage in ['review_images', 'generate_newsletter', 'review_newsletter', 'final'] and st.session_state.description_approved:
        st.markdown("---")
        st.header("Agent 2 & 3: Image Designer Output")

        # Determine approval status for images
        fb_needed = st.session_state.user_inputs['gen_fb']
        ig_needed = st.session_state.user_inputs['gen_ig']
        all_images_approved = (not fb_needed or st.session_state.fb_image_approved) and \
                              (not ig_needed or st.session_state.ig_image_approved)

        col_fb, col_ig = st.columns(2)
        if fb_needed:
            with col_fb:
                st.subheader("Facebook Cover Image")
                if st.session_state.fb_image_url:
                    st.image(st.session_state.fb_image_url, caption="1792x1024")
                    if not st.session_state.fb_image_approved:
                        col_fb1, col_fb2, col_fb3 = st.columns(3)
                        if col_fb1.button("Regenerate FB Image"):
                            st.session_state.fb_image_url = None
                            st.session_state.stage = 'Image Generations'
                            st.rerun()
                        if col_fb2.button("Approve FB Image", type="primary"):
                            st.session_state.fb_image_approved = True
                            st.rerun()
                        if col_fb3.button("Approve without FB Image"):
                            st.session_state.fb_image_approved = True
                            st.session_state.fb_image_url = None # Fallback
                            st.rerun()
                else:
                    st.warning("Facebook image generation failed or was skipped.")

        if ig_needed:
            with col_ig:
                st.subheader("Instagram Post Image")
                if st.session_state.ig_image_url:
                    st.image(st.session_state.ig_image_url, caption="1024x1024")
                    if not st.session_state.ig_image_approved:
                        col_ig1, col_ig2, col_ig3 = st.columns(3)
                        if col_ig1.button("Regenerate IG Image"):
                            st.session_state.ig_image_url = None
                            st.session_state.stage = 'Image Generations'
                            st.rerun()
                        if col_ig2.button("Approve IG Image", type="primary"):
                            st.session_state.ig_image_approved = True
                            st.rerun()
                        if col_ig3.button("Approve without IG Image"):
                            st.session_state.ig_image_approved = True
                            st.session_state.ig_image_url = None # Fallback
                            st.rerun()
                else:
                    st.warning("Instagram image generation failed or was skipped.")

        if all_images_approved and st.session_state.stage == 'review_images':
            st.session_state.stage = 'generate_newsletter'
            st.rerun()

    # --- Agent 4: Newsletter Composer ---
    if st.session_state.stage == 'generate_newsletter' and st.session_state.user_inputs['gen_news']:
        with st.spinner("Composing newsletter..."):
            # Use FB image for newsletter, or IG if FB not available, or no image.
            header_image = st.session_state.fb_image_url or st.session_state.ig_image_url
            if header_image:
                run_newsletter_composer_agent(
                    st.session_state.user_inputs['title'],
                    st.session_state.generated_description,
                    header_image
                )
            else:
                st.warning("No image was approved, generating newsletter without a header image.")
                st.session_state.newsletter_html = f"<h1>{st.session_state.user_inputs['title']}</h1><p>{st.session_state.generated_description.replace('\n', '<br>')}</p>"
        st.session_state.stage = 'review_newsletter'
        st.rerun()
    elif st.session_state.stage == 'generate_newsletter' and not st.session_state.user_inputs['gen_news']:
        st.session_state.stage = 'final' # Skip to final stage
        st.rerun()


    if st.session_state.stage in ['review_newsletter', 'final'] and st.session_state.user_inputs['gen_news']:
        st.markdown("---")
        st.header("Agent 4: Newsletter Composer Output")
        st.subheader("Newsletter Preview")
        st.markdown(st.session_state.newsletter_html, unsafe_allow_html=True)

        st.subheader("Editable HTML Code")
        edited_html = st.text_area("You can edit the HTML code below:", value=st.session_state.newsletter_html, height=300)
        st.session_state.newsletter_html = edited_html

        if not st.session_state.newsletter_approved:
            if st.button("Approve Newsletter", type="primary"):
                st.session_state.newsletter_approved = True
                st.session_state.stage = 'final'
                st.rerun()

    # --- Final Stage: Save and Send ---
    newsletter_needed = st.session_state.user_inputs.get('gen_news', False)
    all_approved = st.session_state.description_approved and \
                   (not st.session_state.user_inputs.get('gen_fb', False) or st.session_state.fb_image_approved) and \
                   (not st.session_state.user_inputs.get('gen_ig', False) or st.session_state.ig_image_approved) and \
                   (not newsletter_needed or st.session_state.newsletter_approved)

    if st.session_state.stage == 'final' and all_approved:
        st.markdown("---")
        st.header("🎉 All Content Approved! 🎉")

        if st.button("💾 Save Event to Database"):
            save_event_to_db()

#        if newsletter_needed:
#            st.subheader("📧 Send Test Newsletter")
#            with st.expander("Configure Gmail Sending"):
#                sender_email = st.text_input("Your Gmail Address")
#                app_password = st.text_input("Your Gmail App Password", type="password")
#                recipient_email = st.text_input("Recipient's Email Address")
#                if st.button("Send Test Email"):
#                    if sender_email and app_password and recipient_email:
#                        send_gmail(
#                            sender_email,
#                            app_password,
#                            recipient_email,
#                            f"Event: {st.session_state.user_inputs['title']}",
#                            st.session_state.newsletter_html
#                        )
#                    else:
#                        st.warning("Please fill in all email fields.")

def view_events_page():
    st.header("View Past Events")
    try:
        conn = sqlite3.connect('events.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM events ORDER BY created_at DESC")
        events = c.fetchall()
        conn.close()

        if not events:
            st.info("No events found in the database yet.")
            return

        # Prepare for JSON download
        events_dict = [dict(event) for event in events]
        json_string = json.dumps(events_dict, indent=4)
        st.download_button(
            label="📥 Download All as JSON",
            data=json_string,
            file_name="events.json",
            mime="application/json",
        )

        for event in events:
            with st.expander(f"**{event['title']}** (Created: {event['created_at']})"):
                st.markdown(f"**Description:**\n```\n{event['description']}\n```")
                if event['newsletter_html']:
                    st.markdown("**Newsletter Preview:**")
                    st.markdown(event['newsletter_html'], unsafe_allow_html=True)
                if event['fb_image_url'] or event['ig_image_url']:
                    st.markdown("**Generated Images:**")
                    col1, col2 = st.columns(2)
                    if event['fb_image_url']:
                        col1.image(event['fb_image_url'], caption="Facebook Image")
                    if event['ig_image_url']:
                        col2.image(event['ig_image_url'], caption="Instagram Image")

    except sqlite3.Error as e:
        st.error(f"Database error while fetching events: {e}")


# --- Main App Logic ---
def main():
    st.title("✨ AI Event Marketing Assistant ✨")
    st.markdown("Your AI-powered partner for creating marketing materials for wellness events.")

    page = st.sidebar.radio("Navigation", ["Create New Event", "View Past Events"])

    if page == "Create New Event":
        create_event_page()
    elif page == "View Past Events":
        view_events_page()


if __name__ == "__main__":
    initialize_database()
    init_session_state()
    main()
