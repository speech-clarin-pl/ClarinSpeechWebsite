from config import db

projects = db.clarin.emu.find({})

for project in projects:
    print(f'Project {project["_id"]}...')
    for name, bundle in project['bundles'].items():
        if 'name' not in bundle:
            bundle['name'] = name
            newname = f'{bundle["session"]}_{bundle["name"]}'
            project['bundles'][newname] = project['bundles'].pop(name)
    db.clarin.emu.replace_one({'_id': project['_id']}, project)
print("Done!")
