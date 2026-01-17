# app/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from datetime import date, datetime
import requests
from sqlalchemy import func

from .models import (
    Farmer,
    Goat,
    Sheep,
    Cattle,
    AggregationBatch,
    ProcessingBatch,
    ContactMessage,
    OrderRequest,
)
from .extensions import db, limiter

main = Blueprint("main", __name__)

# ======================
# reCAPTCHA Verification
# ======================
def verify_recaptcha(response_token: str) -> bool:
    SECRET_KEY = "6Lc1hEksAAAAAJjGH2S0KcW6kyOye7bs927dN_hW"
    if not response_token:
        return False
    try:
        r = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={"secret": SECRET_KEY, "response": response_token},
            timeout=5,
        )
        return r.json().get("success", False)
    except Exception as e:
        print("reCAPTCHA verification failed:", e)
        return False

# ======================
# Dashboard
# ======================
@main.route("/dashboard")
@login_required
def dashboard():
    # Counts
    stats = {}
    stats['farmers'] = Farmer.query.count()
    stats['goats'] = Goat.query.count()
    stats['sheep'] = Sheep.query.count()
    stats['cattle'] = Cattle.query.count()
    stats['aggregation_batches'] = AggregationBatch.query.count()
    stats['processing_batches'] = ProcessingBatch.query.count()

    # Pipelines
    stats['goat_pipeline'] = {
        'on_farm': Goat.query.filter_by(status="on_farm").count(),
        'aggregated': Goat.query.filter_by(status="aggregated").count(),
        'processed': Goat.query.filter_by(status="processed").count(),
        'sold': Goat.query.filter_by(status="sold").count()
    }
    stats['sheep_pipeline'] = {
        'on_farm': Sheep.query.filter_by(status="on_farm").count(),
        'aggregated': Sheep.query.filter_by(status="aggregated").count(),
        'processed': Sheep.query.filter_by(status="processed").count(),
        'sold': Sheep.query.filter_by(status="sold").count()
    }
    stats['cattle_pipeline'] = {
        'on_farm': Cattle.query.filter_by(status="on_farm").count(),
        'aggregated': Cattle.query.filter_by(status="aggregated").count(),
        'processed': Cattle.query.filter_by(status="processed").count(),
        'sold': Cattle.query.filter_by(status="sold").count()
    }

    # Latest messages & orders
    stats['latest_contacts'] = ContactMessage.query.order_by(ContactMessage.created_at.desc()).limit(5).all()
    stats['latest_orders'] = OrderRequest.query.order_by(OrderRequest.created_at.desc()).limit(5).all()

    return render_template("dashboard.html", stats=stats, current_year=datetime.utcnow().year)

# ======================
# Farmer Routes
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
# Animal Utilities
# ======================
def generate_animal_code(animal_type: str, farmer_id: int) -> str:
    year = datetime.utcnow().year
    Model = {"goat": Goat, "sheep": Sheep, "cattle": Cattle}[animal_type]

    last_animal = (
        Model.query
        .filter(
            Model.farmer_id == farmer_id,
            Model.rizara_id.like(f"RZ-%")
        )
        .order_by(Model.created_at.desc())
        .first()
    )

    last_seq = 0
    if last_animal:
        try:
            last_seq = int(last_animal.rizara_id.split("-")[-1])
        except ValueError:
            pass

    return f"RZ-{animal_type.upper()}-{year}-{farmer_id}-{last_seq + 1:03d}"

# ======================
# Add Animals
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
            rizara_id=generate_animal_code("goat", farmer_id),
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


@main.route("/sheep/add", methods=["GET", "POST"])
@login_required
def add_sheep():
    farmers = Farmer.query.all()
    if request.method == "POST":
        farmer_id = int(request.form["farmer_id"])
        farmer = Farmer.query.get_or_404(farmer_id)
        sheep = Sheep(
            farmer_tag=farmer.name,
            rizara_id=generate_animal_code("sheep", farmer_id),
            sex=request.form.get("sex"),
            breed=request.form.get("breed"),
            estimated_dob=request.form.get("estimated_dob"),
            farmer_id=farmer_id,
            status="on_farm"
        )
        db.session.add(sheep)
        db.session.commit()
        flash("Sheep registered successfully", "success")
        return redirect(url_for("main.dashboard"))
    return render_template("sheep/add.html", farmers=farmers)


@main.route("/cattle/add", methods=["GET", "POST"])
@login_required
def add_cattle():
    farmers = Farmer.query.all()
    if request.method == "POST":
        farmer_id = int(request.form["farmer_id"])
        farmer = Farmer.query.get_or_404(farmer_id)
        cattle = Cattle(
            farmer_tag=farmer.name,
            rizara_id=generate_animal_code("cattle", farmer_id),
            sex=request.form.get("sex"),
            breed=request.form.get("breed"),
            estimated_dob=request.form.get("estimated_dob"),
            farmer_id=farmer_id,
            status="on_farm"
        )
        db.session.add(cattle)
        db.session.commit()
        flash("Cattle registered successfully", "success")
        return redirect(url_for("main.dashboard"))
    return render_template("cattle/add.html", farmers=farmers)

# ======================
# Aggregation Batches
# ======================
def aggregation_route(animal_type: str, template_add: str):
    Model = {"goat": Goat, "sheep": Sheep, "cattle": Cattle}[animal_type]
    label = animal_type.capitalize()
    endpoint_name = f"add_{animal_type}_aggregation"

    @main.route(f"/{animal_type}/aggregation/add", methods=["GET", "POST"], endpoint=endpoint_name)
    @login_required
    def add_aggregation():
        available_animals = Model.query.filter_by(status="on_farm").all()
        if request.method == "POST":
            site_name = request.form.get("site_name")
            date_received = request.form.get("date_received")
            animal_ids = request.form.getlist("animal_ids")
            if not site_name or not animal_ids:
                flash("Site name and at least one animal are required", "danger")
                return redirect(request.url)
            batch = AggregationBatch(
                animal_type=animal_type,
                site_name=site_name,
                date_received=datetime.strptime(date_received, "%Y-%m-%d") if date_received else date.today(),
            )
            for a_id in animal_ids:
                animal = Model.query.get(a_id)
                if animal and animal.status == "on_farm":
                    animal.status = "aggregated"
                    if animal_type == "goat":
                        batch.goats.append(animal)
                    elif animal_type == "sheep":
                        batch.sheep.append(animal)
                    elif animal_type == "cattle":
                        batch.cattle.append(animal)
            db.session.add(batch)
            db.session.commit()
            flash(f"{label} aggregation batch created successfully", "success")
            return redirect(url_for("main.dashboard"))
        return render_template(template_add, animals=available_animals)

    return add_aggregation

aggregation_route("goat", "aggregation/goats_add.html")
aggregation_route("sheep", "aggregation/sheep_add.html")
aggregation_route("cattle", "aggregation/cattle_add.html")

# ======================
# Processing Batches
# ======================
def processing_route(animal_type: str, template_add: str):
    Model = {"goat": Goat, "sheep": Sheep, "cattle": Cattle}[animal_type]
    label = animal_type.capitalize()
    endpoint_name = f"add_{animal_type}_processing"

    @main.route(f"/{animal_type}/processing/add", methods=["GET", "POST"], endpoint=endpoint_name)
    @login_required
    def add_processing():
        available_animals = Model.query.filter_by(status="aggregated").all()
        if request.method == "POST":
            facility = request.form.get("facility")
            slaughter_date = request.form.get("slaughter_date")
            halal_cert_ref = request.form.get("halal_cert_ref")
            animal_ids = request.form.getlist("animal_ids")
            if not facility or not animal_ids:
                flash("Facility and at least one animal are required", "danger")
                return redirect(request.url)
            batch = ProcessingBatch(
                animal_type=animal_type,
                facility=facility,
                slaughter_date=datetime.strptime(slaughter_date, "%Y-%m-%d") if slaughter_date else None,
                halal_cert_ref=halal_cert_ref,
            )
            animals = Model.query.filter(Model.id.in_(animal_ids)).all()
            for animal in animals:
                if animal.status == "aggregated":
                    animal.status = "processed"
                    if animal_type == "goat":
                        batch.goats.append(animal)
                    elif animal_type == "sheep":
                        batch.sheep.append(animal)
                    elif animal_type == "cattle":
                        batch.cattle.append(animal)
            db.session.add(batch)
            db.session.commit()
            flash(f"{label} processing batch created successfully", "success")
            return redirect(url_for("main.dashboard"))
        return render_template(template_add, animals=available_animals)

    return add_processing

processing_route("goat", "processing/goats_add.html")
processing_route("sheep", "processing/sheep_add.html")
processing_route("cattle", "processing/cattle_add.html")

# ======================
# Public Forms
# ======================
@main.route("/submit-contact", methods=["POST"])
@limiter.limit("5 per minute")
def submit_contact():
    if request.form.get("hp_field"):
        return jsonify({"success": False}), 200
    if not verify_recaptcha(request.form.get("g-recaptcha-response")):
        return jsonify({"success": False}), 403
    name = request.form.get("name")
    email = request.form.get("email")
    phone = request.form.get("phone")
    message = request.form.get("message")
    if not name or not email or not message:
        return jsonify({"success": False}), 400
    contact = ContactMessage(
        name=name,
        email=email,
        subject=f"Website contact form - {phone}",
        message=message,
        status="new",
    )
    db.session.add(contact)
    db.session.commit()
    return jsonify({"success": True}), 200

@main.route("/submit-order", methods=["POST"])
@limiter.limit("3 per minute")
def submit_order():
    if request.form.get("hp_field"):
        return jsonify({"success": False}), 200
    if not verify_recaptcha(request.form.get("g-recaptcha-response")):
        return jsonify({"success": False}), 403
    buyer_name = request.form.get("buyerName")
    email = request.form.get("email")
    phone = request.form.get("phone")
    product = request.form.get("product")
    quantity = request.form.get("quantity")
    destination = request.form.get("destination")
    notes = request.form.get("message")
    if not all([buyer_name, email, phone, product, quantity, destination]):
        return jsonify({"success": False}), 400
    order = OrderRequest(
        buyer_name=buyer_name,
        phone=phone,
        email=email,
        product=product,
        quantity=int(quantity),
        delivery_location=destination,
        notes=notes,
        status="new",
    )
    db.session.add(order)
    db.session.commit()
    return jsonify({"success": True}), 200

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

# ======================
# Animal Pipeline Views
# ======================
@main.route("/animals/<animal_type>/<status>")
@login_required
def animal_pipeline_view(animal_type, status):
    ModelMap = {"goat": Goat, "sheep": Sheep, "cattle": Cattle}
    if animal_type not in ModelMap:
        flash("Invalid animal type", "danger")
        return redirect(url_for("main.dashboard"))
    if status not in ["on_farm", "aggregated", "processed", "sold"]:
        flash("Invalid status", "danger")
        return redirect(url_for("main.dashboard"))

    Model = ModelMap[animal_type]
    animals = Model.query.filter_by(status=status).order_by(Model.created_at.desc()).all()

    return render_template(
        "animals/pipeline_list.html",
        animals=animals,
        animal_type=animal_type,
        status=status
    )
