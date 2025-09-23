# org_routes.py
from flask import request, jsonify
from models import db, User
from models import Organization, OrgMembership  # los agregas en el paso 2.3-A (abajo)

def register_org_routes(app):

    def _require_bearer_token():
        auth = request.headers.get("Authorization","")
        if not auth.startswith("Bearer "):
            return None
        return auth.split(" ",1)[1]

    def _decode_jwt(token):
        # Si ya tienes una función real en auth.py, úsala:
        try:
            from auth import decode_access  # si existe
            return decode_access(token)
        except:
            return {"sub": None, "roles": []}

    def _get_current_user():
        token = _require_bearer_token()
        if not token:
            return None
        claims = _decode_jwt(token)
        if not claims or "sub" not in claims:
            return None
        return User.query.get(claims["sub"])

    @app.route("/orgs", methods=["POST"])
    def create_org():
        me = _get_current_user()
        if not me:
            return jsonify({"error":"unauthorized"}), 401
        data = request.get_json(force=True) or {}
        name = data.get("name")
        if not name or len(name) < 2:
            return jsonify({"error":"invalid name"}), 400
        org = Organization(name=name, status="active")
        db.session.add(org); db.session.commit()
        db.session.add(OrgMembership(user_id=me.id, org_id=org.id, role="owner"))
        db.session.commit()
        return jsonify({"id": org.id, "name": org.name, "status": org.status})

    @app.route("/orgs/<org_id>/users", methods=["POST"])
    def org_add_user(org_id):
        me = _get_current_user()
        if not me:
            return jsonify({"error":"unauthorized"}), 401

        org = Organization.query.get(org_id)
        if not org or org.status != "active":
            return jsonify({"error":"org not found"}), 404

        my_mem = OrgMembership.query.filter_by(user_id=me.id, org_id=org_id).first()
        if not my_mem or my_mem.role not in ("owner","manager"):
            return jsonify({"error":"forbidden"}), 403

        data = request.get_json(force=True) or {}
        username = data.get("username")
        role     = data.get("role","agent")
        if role not in ("owner","manager","agent","viewer","suspended"):
            return jsonify({"error":"invalid role"}), 400

        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({"error":"user not found"}), 404

        mem = OrgMembership.query.filter_by(user_id=user.id, org_id=org_id).first()
        if not mem:
            mem = OrgMembership(user_id=user.id, org_id=org_id, role=role)
            db.session.add(mem)
        else:
            mem.role = role
        db.session.commit()
        return jsonify({"username": user.username, "role": role})

    @app.route("/orgs/<org_id>/users", methods=["GET"])
    def org_list_users(org_id):
        me = _get_current_user()
        if not me:
            return jsonify({"error":"unauthorized"}), 401
        org = Organization.query.get(org_id)
        if not org or org.status != "active":
            return jsonify({"error":"org not found"}), 404

        my_mem = OrgMembership.query.filter_by(user_id=me.id, org_id=org_id).first()
        if not my_mem:
            return jsonify({"error":"forbidden"}), 403

        q = db.session.query(User.username, OrgMembership.role).join(
            OrgMembership, OrgMembership.user_id == User.id
        ).filter(OrgMembership.org_id == org_id)

        return jsonify([{"username": u, "role": r} for (u, r) in q.all()])
