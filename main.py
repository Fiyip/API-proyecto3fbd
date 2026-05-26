from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ── Conexión MongoDB ──────────────────────────────────────────────
MONGO_URI = "mongodb://ISIS2304J13202610:SwaJFnAt1RGe@157.253.236.88:8087"
client     = MongoClient(MONGO_URI)
db         = client["ISIS2304J13202610"]
reviews    = db["dann_alpes_reviews"]
votos      = db["dann_alpes_votos_utilidad"]

# Helper para serializar ObjectId
def serialize(doc):
    if doc is None:
        return None
    doc["_id"] = str(doc["_id"])
    return doc

# ═══════════════════════════════════════════════════════════════════
#  RF1 – Crear reseña
# ═══════════════════════════════════════════════════════════════════
@app.route("/resenas", methods=["POST"])
def crear_resena():
    data = request.get_json()
    reserva_id  = data.get("reserva_id")
    cliente_id  = data.get("cliente_id")
    hotel_id    = data.get("hotel_id")
    calificacion = data.get("calificacion")
    comentario  = data.get("comentario")
    ciudad      = data.get("ciudad", "")

    if not all([reserva_id, cliente_id, hotel_id, calificacion, comentario]):
        return jsonify({"error": "Faltan campos obligatorios"}), 400

    # Validar que no exista ya una reseña para esa reserva
    existe = reviews.find_one({"reserva_id": reserva_id, "estado": {"$ne": "eliminada"}})
    if existe:
        return jsonify({"error": "Ya existe una reseña para esta reserva"}), 409

    nueva = {
        "hotel_id":       hotel_id,
        "cliente_id":     cliente_id,
        "reserva_id":     reserva_id,
        "ciudad":         ciudad,
        "fecha_creacion": datetime.utcnow().strftime("%Y-%m-%d"),
        "calificacion":   int(calificacion),
        "comentario":     comentario,
        "estado":         "publicada",
        "total_utilidad": 0,
        "destacada":      False,
        "respuesta_admin": {}
    }
    result = reviews.insert_one(nueva)
    return jsonify({"mensaje": "Reseña creada", "id": str(result.inserted_id)}), 201


# ═══════════════════════════════════════════════════════════════════
#  RF2 – Editar reseña
# ═══════════════════════════════════════════════════════════════════
@app.route("/resenas/<resena_id>", methods=["PUT"])
def editar_resena(resena_id):
    data = request.get_json()
    update = {}
    if "calificacion" in data:
        update["calificacion"] = int(data["calificacion"])
    if "comentario" in data:
        update["comentario"] = data["comentario"]

    if not update:
        return jsonify({"error": "Nada que actualizar"}), 400

    try:
        result = reviews.update_one({"_id": ObjectId(resena_id)}, {"$set": update})
    except Exception:
        return jsonify({"error": "ID inválido"}), 400

    if result.matched_count == 0:
        return jsonify({"error": "Reseña no encontrada"}), 404
    return jsonify({"mensaje": "Reseña actualizada"}), 200


# ═══════════════════════════════════════════════════════════════════
#  RF3 – Eliminar reseña (cliente)
# ═══════════════════════════════════════════════════════════════════
@app.route("/resenas/<resena_id>", methods=["DELETE"])
def eliminar_resena(resena_id):
    cliente_id = request.args.get("cliente_id")
    try:
        query = {"_id": ObjectId(resena_id)}
        if cliente_id:
            query["cliente_id"] = cliente_id
        result = reviews.update_one(query, {"$set": {"estado": "eliminada"}})
    except Exception:
        return jsonify({"error": "ID inválido"}), 400

    if result.matched_count == 0:
        return jsonify({"error": "Reseña no encontrada"}), 404
    return jsonify({"mensaje": "Reseña eliminada"}), 200


# ═══════════════════════════════════════════════════════════════════
#  RF4 – Consultar reseñas de un hotel (paginadas, ordenadas)
# ═══════════════════════════════════════════════════════════════════
@app.route("/resenas/hotel/<hotel_id>", methods=["GET"])
def consultar_resenas_hotel(hotel_id):
    orden    = request.args.get("orden", "fecha")   # fecha | utilidad
    pagina   = int(request.args.get("pagina", 1))
    por_pag  = int(request.args.get("por_pagina", 10))
    skip     = (pagina - 1) * por_pag

    sort_field = "fecha_creacion" if orden == "fecha" else "total_utilidad"

    # Reseña destacada primero
    destacada = reviews.find_one({"hotel_id": hotel_id, "destacada": True, "estado": "publicada"})

    cursor = reviews.find(
        {"hotel_id": hotel_id, "estado": "publicada", "destacada": {"$ne": True}},
        {"hotel_id":1,"cliente_id":1,"fecha_creacion":1,"calificacion":1,
         "comentario":1,"total_utilidad":1,"respuesta_admin":1,"destacada":1}
    ).sort(sort_field, -1).skip(skip).limit(por_pag)

    resultado = []
    if destacada and pagina == 1:
        resultado.append(serialize(destacada))
    resultado += [serialize(r) for r in cursor]

    total = reviews.count_documents({"hotel_id": hotel_id, "estado": "publicada"})
    return jsonify({"total": total, "pagina": pagina, "resenas": resultado}), 200


# ═══════════════════════════════════════════════════════════════════
#  RF5 – Marcar reseña como útil
# ═══════════════════════════════════════════════════════════════════
@app.route("/votos", methods=["POST"])
def marcar_util():
    data       = request.get_json()
    resena_id  = data.get("resena_id")
    cliente_id = data.get("cliente_id")

    if not resena_id or not cliente_id:
        return jsonify({"error": "Faltan campos"}), 400

    ya_voto = votos.find_one({"resena_id": resena_id, "cliente_id": cliente_id})
    if ya_voto:
        return jsonify({"error": "Ya votaste esta reseña"}), 409

    votos.insert_one({
        "resena_id":  resena_id,
        "cliente_id": cliente_id,
        "fecha_voto": datetime.utcnow().strftime("%Y-%m-%d")
    })
    reviews.update_one({"_id": ObjectId(resena_id)}, {"$inc": {"total_utilidad": 1}})
    return jsonify({"mensaje": "Voto registrado"}), 201


# ═══════════════════════════════════════════════════════════════════
#  RF6 – Historial de reseñas propias
# ═══════════════════════════════════════════════════════════════════
@app.route("/resenas/cliente/<cliente_id>", methods=["GET"])
def historial_cliente(cliente_id):
    orden = request.args.get("orden", "fecha")  # fecha | hotel
    sort_field = "fecha_creacion" if orden == "fecha" else "hotel_id"

    cursor = reviews.find(
        {"cliente_id": cliente_id},
        {"hotel_id":1,"fecha_creacion":1,"calificacion":1,"estado":1,
         "total_utilidad":1,"respuesta_admin":1,"comentario":1}
    ).sort(sort_field, -1)

    resultado = [serialize(r) for r in cursor]
    return jsonify(resultado), 200


# ═══════════════════════════════════════════════════════════════════
#  RF7 – Responder reseña (admin)
# ═══════════════════════════════════════════════════════════════════
@app.route("/resenas/<resena_id>/respuesta", methods=["POST"])
def responder_resena(resena_id):
    data = request.get_json()
    administrador_id = data.get("administrador_id")
    texto            = data.get("texto_respuesta")

    if not administrador_id or not texto:
        return jsonify({"error": "Faltan campos"}), 400

    respuesta = {
        "administrador_id": administrador_id,
        "texto_respuesta":  texto,
        "fecha_respuesta":  datetime.utcnow().strftime("%Y-%m-%d")
    }
    try:
        result = reviews.update_one(
            {"_id": ObjectId(resena_id)},
            {"$set": {"respuesta_admin": respuesta}}
        )
    except Exception:
        return jsonify({"error": "ID inválido"}), 400

    if result.matched_count == 0:
        return jsonify({"error": "Reseña no encontrada"}), 404
    return jsonify({"mensaje": "Respuesta guardada"}), 200


# ═══════════════════════════════════════════════════════════════════
#  RF8 – Eliminar reseña (admin)
# ═══════════════════════════════════════════════════════════════════
@app.route("/admin/resenas/<resena_id>", methods=["DELETE"])
def eliminar_resena_admin(resena_id):
    try:
        result = reviews.update_one(
            {"_id": ObjectId(resena_id)},
            {"$set": {"estado": "eliminada"}}
        )
    except Exception:
        return jsonify({"error": "ID inválido"}), 400

    if result.matched_count == 0:
        return jsonify({"error": "Reseña no encontrada"}), 404
    return jsonify({"mensaje": "Reseña eliminada por administrador"}), 200


# ═══════════════════════════════════════════════════════════════════
#  RF9 – Destacar reseña (solo una por hotel)
# ═══════════════════════════════════════════════════════════════════
@app.route("/resenas/<resena_id>/destacar", methods=["POST"])
def destacar_resena(resena_id):
    try:
        resena = reviews.find_one({"_id": ObjectId(resena_id)})
    except Exception:
        return jsonify({"error": "ID inválido"}), 400

    if not resena:
        return jsonify({"error": "Reseña no encontrada"}), 404

    hotel_id = resena["hotel_id"]
    # Quitar destacada anterior del mismo hotel
    reviews.update_many({"hotel_id": hotel_id}, {"$set": {"destacada": False}})
    # Destacar la nueva
    reviews.update_one({"_id": ObjectId(resena_id)}, {"$set": {"destacada": True}})
    return jsonify({"mensaje": "Reseña destacada"}), 200


# ═══════════════════════════════════════════════════════════════════
#  RFC1 – Top 10 hoteles por calificación promedio en un período
# ═══════════════════════════════════════════════════════════════════
@app.route("/consultas/top-hoteles", methods=["GET"])
def top_hoteles():
    fecha_ini = request.args.get("fecha_inicio", "2026-01-01")
    fecha_fin = request.args.get("fecha_fin",    "2026-12-31")

    pipeline = [
        {"$match": {
            "estado": "publicada",
            "fecha_creacion": {"$gte": fecha_ini, "$lte": fecha_fin}
        }},
        {"$group": {
            "_id": "$hotel_id",
            "promedio_calificacion": {"$avg": "$calificacion"},
            "total_resenas": {"$sum": 1}
        }},
        {"$sort": {"promedio_calificacion": -1}},
        {"$limit": 10}
    ]
    resultado = list(reviews.aggregate(pipeline))
    return jsonify(resultado), 200


# ═══════════════════════════════════════════════════════════════════
#  RFC2 – Evolución de reputación mes a mes de un hotel
# ═══════════════════════════════════════════════════════════════════
@app.route("/consultas/evolucion/<hotel_id>", methods=["GET"])
def evolucion_hotel(hotel_id):
    pipeline = [
        {"$match": {"hotel_id": hotel_id, "estado": "publicada"}},
        {"$addFields": {
            "fecha_date": {"$dateFromString": {"dateString": "$fecha_creacion"}}
        }},
        {"$group": {
            "_id": {
                "mes":  {"$month":  "$fecha_date"},
                "anio": {"$year":   "$fecha_date"}
            },
            "promedio_calificacion": {"$avg": "$calificacion"},
            "total_resenas": {"$sum": 1}
        }},
        {"$sort": {"_id.anio": 1, "_id.mes": 1}}
    ]
    resultado = list(reviews.aggregate(pipeline))
    return jsonify(resultado), 200


# ═══════════════════════════════════════════════════════════════════
#  RFC3 – Perfil comparativo de hoteles por ciudad
# ═══════════════════════════════════════════════════════════════════
@app.route("/consultas/comparativo/<ciudad>", methods=["GET"])
def comparativo_ciudad(ciudad):
    pipeline = [
        {"$match": {"ciudad": ciudad, "estado": "publicada"}},
        {"$group": {
            "_id": "$hotel_id",
            "promedio_calificacion": {"$avg": "$calificacion"},
            "total_resenas":         {"$sum": 1},
            "con_respuesta": {"$sum": {"$cond": [{"$ifNull": ["$respuesta_admin", False]}, 1, 0]}},
            "destacadas":    {"$sum": {"$cond": [{"$eq": ["$destacada", True]}, 1, 0]}}
        }},
        {"$addFields": {
            "porcentaje_respuesta":  {"$multiply": [{"$divide": ["$con_respuesta", "$total_resenas"]}, 100]},
            "porcentaje_destacadas": {"$multiply": [{"$divide": ["$destacadas",    "$total_resenas"]}, 100]}
        }},
        {"$sort": {"promedio_calificacion": -1}}
    ]
    resultado = list(reviews.aggregate(pipeline))

    # Promedio general de la ciudad para identificar hoteles por debajo
    if resultado:
        prom_ciudad = sum(r["promedio_calificacion"] for r in resultado) / len(resultado)
        for r in resultado:
            r["bajo_promedio_ciudad"] = r["promedio_calificacion"] < prom_ciudad
    return jsonify({"promedio_ciudad": prom_ciudad if resultado else 0, "hoteles": resultado}), 200


# ═══════════════════════════════════════════════════════════════════
#  Health check
# ═══════════════════════════════════════════════════════════════════
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "OK", "mensaje": "API Dann-Alpes activa"}), 200


if __name__ == "__main__":
    app.run(debug=True)
