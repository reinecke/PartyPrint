from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

import os
#engine_url = ('sqlite:///' + 
#        os.path.dirname(os.path.abspath(__file__)) + '/test.db')
# TODO: Move to common config file
USER = "DB_USERNAME"
PASS = "DB_PASSWORD"

engine_url = "mysql://%s:%s@mysql.myhost.com/database_name"
print "database at:", engine_url%(USER, "****")

engine = create_engine(engine_url%(USER, PASS), convert_unicode=True)
#engine.execute("USE partyprint")
db_session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))
Base = declarative_base()
Base.query = db_session.query_property()

def init_db():
    # import all modules here that might define models so that
    # they will be registered properly on the metadata.  Otherwise
    # you will have to import them first before calling init_db()
    import models
    Base.metadata.create_all(bind=engine)
