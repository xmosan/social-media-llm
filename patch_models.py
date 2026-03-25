with open("app/models.py", "r") as f:
    text = f.read()

target = """class MediaAsset(Base):
    __tablename__ = "media_assets\""""

repl = """class UserInteraction(Base):
    __tablename__ = "user_interactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action_type = Column(String, nullable=False) # e.g. "selected_topic", "used_entry"
    entity_id = Column(String, nullable=True) # ID or Slug
    context = Column(String, nullable=True) # e.g. "composer", "automation", "library"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class MediaAsset(Base):
    __tablename__ = "media_assets\""""

text = text.replace(target, repl)

with open("app/models.py", "w") as f:
    f.write(text)

print("Models patched.")
