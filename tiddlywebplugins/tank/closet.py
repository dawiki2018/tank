"""
POST binaries to alternate storage, create a canonical uri tiddler
pointing to that storage.
"""

from httpexceptor import HTTP400
from uuid import uuid4
from mimetypes import guess_extension
from boto.s3.connection import S3Connection
from boto.s3.key import Key

from tiddlyweb.model.bag import Bag
from tiddlyweb.model.tiddler import Tiddler
from tiddlyweb.web.util import get_route_value, tiddler_url
from tiddlywebplugins.utils import require_role


@require_role('MEMBER')
def closet(environ, start_response):
    """
    Read file input and write it to special storage.
    """
    store = environ['tiddlyweb.store']
    usersign = environ['tiddlyweb.usersign']
    bag_name = get_route_value(environ, 'bag_name')

    bag = store.get(Bag(bag_name))

    bag.policy.allows(usersign, 'create')
    bag.policy.allows(usersign, 'write')

    files = environ['tiddlyweb.input_files']

    if not files:
        raise HTTP400('missing file input')

    tiddlers = []
    for input_file in files:
        filename = input_file.filename
        binary_storage = BinaryDisk(environ, input_file)
        url = binary_storage.store()
        tiddler = Tiddler(filename, bag_name)
        tiddler.fields['_canonical_uri'] = url
        tiddler.modifier = usersign['name']
        tiddler.type = input_file.type
        store.put(tiddler)
        tiddlers.append(tiddler)

    print 'tiddlers', tiddlers
    start_response('303 See Other', [
        ('Location', tiddler_url(environ, tiddlers[-1]))])
    return []


class BinaryDisk(object):

    Disk = 'closet'

    def __init__(self, environ, filething):
        self.environ = environ
        self.filename = filething.name
        self.filehandle = filething.file
        self.type = filething.type
        self.extension = guess_extension(self.type) or ''
        self.targetname = uuid4().get_hex() + self.extension

        self.config = environ['tiddlyweb.config']
        self.boto = S3Connection(self.config['closet.aws_access_key'],
                self.config['closet.aws_secret_key'])

    def store(self):
        bucket = self.boto.create_bucket(self.config['closet.bucket'])
        key = Key(bucket)
        key.key = self.targetname
        key.set_metadata('Content-Type', self.type)
        key.set_contents_from_file(self.filehandle)
        url = key.generate_url(0, query_auth=False)
        return url