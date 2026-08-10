from app.items import service
from app.items.exceptions import ItemNotFound
from app.user.dependencies import owned_resource

# Resolves `{resource_id}`, 404s if it doesn't exist *or* belongs to someone
# else. Admins bypass the ownership check. Routes get the row already loaded.
valid_item = owned_resource(service.get_by_id, not_found=ItemNotFound)
