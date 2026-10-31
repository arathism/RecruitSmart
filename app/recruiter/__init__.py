from flask import Blueprint
bp = Blueprint('recruiter', __name__)
from app.recruiter import routes
