from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from datetime import date, datetime

from .models import Farmer, Goat, AggregationBatch, ProcessingBatch
from .extensions import db

main = Blueprint("main", __name__)


# ======================
# Farmers
# ======================
@main.route("/farmers/add", methods=["GET", "POST"])
@login_required
def add_farmer():
    if request.method == "POST":
        farmer = Farmer(
            name=request.form["name"],
            phone=request.form["phone"],
            county=request.form["county"],
            ward=request.form["ward"],
            village=request.form.get("village"),
            latitude=request.form.get("latitude") or None,
            longitude=request.form.get("longitude") or None,
            location_notes=request.form.get("location_notes"),
        )
        db.session.add(farmer)
        db.session.commit()

        flash("Farmer added successfully", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("farmers/add.html")


# ======================
# Goat Utilities
# ======================
def generate_goat_code(farmer_id: int) -> str:
    """Generate a unique goat code per farmer per year."""
    year = datetime.utcnow().year

    last_goat = (
        Goat.query
        .filter(
            Goat.farmer_id == farmer_id,
            Goat.rizara_id.like(f"RZ-GT-{year}-{farmer_id}-%")
        )
        .order_by(Goat.created_at.desc())
        .first()
    )

    if last_goat:
        try:
            last_seq = int(last_goat.rizara_id.split("-")[-1])
        except ValueError:
            last_seq = 0
    else:
        last_seq = 0

    return f"RZ-GT-{year}-{farmer_id}-{last_seq + 1:03d}"


# ======================
# Goats
# ======================
@main.route("/goats/add", methods=["GET", "POST"])
@login_required
def add_goat():
    farmers = Farmer.query.all()

    if request.method == "POST":
        farmer_id = int(request.form["farmer_id"])
        farmer = Farmer.query.get_or_404(farmer_id)

        goat = Goat(
            farmer_tag=farmer.name,
            rizara_id=generate_goat_code(farmer_id),
            sex=request.form.get("sex"),
            breed=request.form.get("breed"),
            estimated_dob=request.form.get("estimated_dob"),
            farmer_id=farmer_id,
            status="on_farm"
        )

        db.session.add(goat)
        db.session.commit()

        flash("Goat registered successfully", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("goats/add.html", farmers=farmers)


# ======================
# Aggregation
# ======================
@main.route("/aggregation/add", methods=["GET", "POST"])
@login_required
def add_aggregation_batch():

    # Only goats still on farm can be aggregated
    available_goats = Goat.query.filter_by(status="on_farm").all()

    if request.method == "POST":
        site_name = request.form.get("site_name")
        date_received = request.form.get("date_received")
        goat_ids = request.form.getlist("goat_ids")

        if not site_name or not goat_ids:
            flash("Site name and at least one goat are required", "danger")
            return redirect(request.url)

        batch = AggregationBatch(
            site_name=site_name,
            date_received=datetime.strptime(date_received, "%Y-%m-%d")
            if date_received else date.today()
        )

        for goat_id in goat_ids:
            goat = Goat.query.get(goat_id)
            if goat and goat.status == "on_farm":
                batch.goats.append(goat)
                goat.status = "aggregated"

        db.session.add(batch)
        db.session.commit()

        flash("Aggregation batch created successfully", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("aggregation/add.html", goats=available_goats)


# ======================
# Aggregation List
# ======================
@main.route("/aggregation")
@login_required
def list_aggregation_batches():
    batches = AggregationBatch.query.order_by(
        AggregationBatch.date_received.desc()
    ).all()
    return render_template("aggregation/list.html", batches=batches)


# ======================
# Processing
# ======================
@main.route("/processing/add", methods=["GET", "POST"])
@login_required
def add_processing_batch():

    # Only aggregated goats can be processed
    available_goats = Goat.query.filter_by(status="aggregated").all()

    if request.method == "POST":
        facility = request.form.get("facility")
        slaughter_date = request.form.get("slaughter_date")
        halal_cert_ref = request.form.get("halal_cert_ref")
        goat_ids = request.form.getlist("goat_ids")

        if not facility or not goat_ids:
            flash("Facility and at least one goat are required", "danger")
            return redirect(request.url)

        batch = ProcessingBatch(
            facility=facility,
            slaughter_date=datetime.strptime(slaughter_date, "%Y-%m-%d")
            if slaughter_date else None,
            halal_cert_ref=halal_cert_ref
        )

        goats = Goat.query.filter(Goat.id.in_(goat_ids)).all()

        for goat in goats:
            if goat.status != "aggregated":
                continue
            goat.status = "processed"
            batch.goats.append(goat)

        db.session.add(batch)
        db.session.commit()

        flash("Processing batch created successfully", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("processing/add.html", goats=available_goats)


# ======================
# Processing List
# ======================
@main.route("/processing")
@login_required
def list_processing_batches():
    batches = ProcessingBatch.query.order_by(
        ProcessingBatch.slaughter_date.desc()
    ).all()
    return render_template("processing/list.html", batches=batches)

# ======================
# Contact Form Submission
# ======================
from .models import ContactMessage, OrderRequest  # make sure models are imported

@main.route("/submit-contact", methods=["POST"])
def submit_contact():
    # Honeypot check
    if request.form.get("hp_field"):
        return redirect("/contact.html")  # silently ignore bots

    name = request.form.get("name")
    email = request.form.get("email")
    phone = request.form.get("phone")
    message = request.form.get("message")

    if not name or not email or not message:
        flash("Please fill all required fields", "error")
        return redirect("/contact.html")

    contact = ContactMessage(
        name=name,
        email=email,
        subject=f"From website contact form - {phone}",
        message=message,
        status="new"
    )
    db.session.add(contact)
    db.session.commit()

    flash("Your message has been sent. We will get back to you shortly.", "success")
    return redirect("/contact.html")


# ======================
# Order Form Submission
# ======================
@main.route("/submit-order", methods=["POST"])
def submit_order():
    # Honeypot check
    if request.form.get("hp_field"):
        return redirect("/orders.html")  # silently ignore bots

    buyer_name = request.form.get("buyerName")
    company_name = request.form.get("companyName")
    email = request.form.get("email")
    phone = request.form.get("phone")
    product = request.form.get("product")
    quantity = request.form.get("quantity")
    delivery_location = request.form.get("destination")
    notes = request.form.get("message")  # optional

    if not buyer_name or not email or not phone or not product or not quantity or not delivery_location:
        flash("Please fill all required fields", "error")
        return redirect("/orders.html")

    order = OrderRequest(
        buyer_name=buyer_name,
        phone=phone,
        email=email,
        product=product,
        quantity=int(quantity),
        delivery_location=delivery_location,
        status="new"
    )
    db.session.add(order)
    db.session.commit()

    flash("Your order request has been submitted. Our team will contact you shortly.", "success")
    return redirect("/orders.html")

# ======================
# Admin: Contact Messages
# ======================
@main.route("/admin/contact-messages")
@login_required
def contact_messages():
    messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
    return render_template("admin/contact_messages.html", messages=messages)


@main.route("/admin/contact-messages/<int:msg_id>/update-status", methods=["POST"])
@login_required
def update_contact_status(msg_id):
    new_status = request.form.get("status")
    message = ContactMessage.query.get_or_404(msg_id)
    if new_status in ["new", "reviewed", "closed"]:
        message.status = new_status
        db.session.commit()
        flash("Message status updated.", "success")
    else:
        flash("Invalid status.", "error")
    return redirect(url_for("main.contact_messages"))


# ======================
# Admin: Order Requests
# ======================
@main.route("/admin/order-requests")
@login_required
def order_requests():
    orders = OrderRequest.query.order_by(OrderRequest.created_at.desc()).all()
    return render_template("admin/order_requests.html", orders=orders)


@main.route("/admin/order-requests/<int:order_id>/update-status", methods=["POST"])
@login_required
def update_order_status(order_id):
    new_status = request.form.get("status")
    order = OrderRequest.query.get_or_404(order_id)
    if new_status in ["new", "reviewed", "approved", "rejected"]:
        order.status = new_status
        db.session.commit()
        flash("Order status updated.", "success")
    else:
        flash("Invalid status.", "error")
    return redirect(url_for("main.order_requests"))

# ======================
# Dashboard / Index
# ======================
@main.route("/")
@login_required
def dashboard():
    # KPI counts
    stats = {
        "farmers": Farmer.query.count(),
        "goats": Goat.query.count(),
        "aggregation_batches": AggregationBatch.query.count(),
        "processing_batches": ProcessingBatch.query.count(),
        "goats_on_farm": Goat.query.filter_by(status="on_farm").count(),
        "goats_aggregated": Goat.query.filter_by(status="aggregated").count(),
        "goats_processed": Goat.query.filter_by(status="processed").count(),
        "goats_sold": Goat.query.filter_by(status="sold").count(),
    }

    # Latest 5 contact messages
    stats["latest_contacts"] = (
        ContactMessage.query.order_by(ContactMessage.created_at.desc())
        .limit(5)
        .all()
    )

    # Latest 5 order requests
    stats["latest_orders"] = (
        OrderRequest.query.order_by(OrderRequest.created_at.desc())
        .limit(5)
        .all()
    )

    return render_template("dashboard.html", stats=stats, current_year=datetime.utcnow().year)
