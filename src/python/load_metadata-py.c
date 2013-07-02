/* createrepo_c - Library of routines for manipulation with repodata
 * Copyright (C) 2013  Tomas Mlcoch
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License
 * as published by the Free Software Foundation; either version 2
 * of the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
 * USA.
 */

#include <Python.h>
#include <assert.h>
#include <stddef.h>

#include "load_metadata-py.h"
#include "locate_metadata-py.h"
#include "package-py.h"
#include "exception-py.h"
#include "typeconversion.h"
#include "metadata_hashtable.h"

/* TODO:
 * keys() and records() method (same method - alias only)
 **/

typedef struct {
    PyObject_HEAD
    cr_Metadata *md;
} _MetadataObject;

static int
check_MetadataStatus(const _MetadataObject *self)
{
    assert(self != NULL);
    assert(MetadataObject_Check(self));
    if (self->md == NULL) {
        PyErr_SetString(PyExc_TypeError, "Improper createrepo_c Metadata object.");
        return -1;
    }
    return 0;
}

/* Function on the type */

static PyObject *
metadata_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    CR_UNUSED(args);
    CR_UNUSED(kwds);

    _MetadataObject *self = (_MetadataObject *)type->tp_alloc(type, 0);
    if (self)
        self->md = NULL;
    return (PyObject *)self;
}

static int
metadata_init(_MetadataObject *self, PyObject *args, PyObject *kwds)
{
    static char *kwlist[] = { "key", "use_single_chunk", "pkglist", NULL };
    int key = CR_HT_KEY_DEFAULT;
    int use_single_chunk = 0;
    PyObject *py_pkglist = NULL;
    GSList *pkglist = NULL;

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|iiO!:metadata_init", kwlist,
                          &key, &use_single_chunk, &PyList_Type, &py_pkglist))
        return -1;

    /* Free all previous resources when reinitialization */
    if (self->md) {
        cr_metadata_free(self->md);
    }

    /* Init */
    pkglist = GSList_FromPyList_Str(py_pkglist);
    self->md = cr_metadata_new(key, use_single_chunk, pkglist);
    g_slist_free(pkglist);
    if (self->md == NULL) {
        PyErr_SetString(CrErr_Exception, "Metadata initialization failed");
        return -1;
    }
    return 0;
}

static void
metadata_dealloc(_MetadataObject *self)
{
    if (self->md)
        cr_metadata_free(self->md);
    Py_TYPE(self)->tp_free(self);
}

static PyObject *
metadata_repr(_MetadataObject *self)
{
    CR_UNUSED(self);
    return PyString_FromFormat("<createrepo_c.Metadata object>");
}

/* Getters */

static PyObject *
get_key(_MetadataObject *self, void *nothing)
{
    CR_UNUSED(nothing);
    if (check_MetadataStatus(self))
        return NULL;
    cr_HashTableKey val = cr_metadata_key(self->md);
    return PyLong_FromLong((long) val);
}

static PyGetSetDef metadata_getsetters[] = {
    {"key", (getter)get_key, NULL, NULL, NULL},
    {NULL, NULL, NULL, NULL, NULL} /* sentinel */
};

/* Metadata methods */

static PyObject *
load_xml(_MetadataObject *self, PyObject *args)
{
    PyObject *ml;
    GError *tmp_err = NULL;

    if (!PyArg_ParseTuple(args, "O!:load_xml", &MetadataLocation_Type, &ml))
        return NULL;

    if (check_MetadataStatus(self))
        return NULL;

    cr_metadata_load_xml(self->md, MetadataLocation_FromPyObject(ml), &tmp_err);
    if (tmp_err) {
        nice_exception(&tmp_err, NULL);
        return NULL;
    }

    Py_RETURN_NONE;
}

static PyObject *
locate_and_load_xml(_MetadataObject *self, PyObject *args)
{
    char *path;
    GError *tmp_err = NULL;

    if (!PyArg_ParseTuple(args, "s:locate_and_load_xml", &path))
        return NULL;

    if (check_MetadataStatus(self))
        return NULL;

    cr_metadata_locate_and_load_xml(self->md, path, &tmp_err);
    if (tmp_err) {
        nice_exception(&tmp_err, NULL);
        return NULL;
    }
    Py_RETURN_NONE;
}

/* Hashtable methods */

static PyObject *
ht_len(_MetadataObject *self, PyObject *noarg)
{
    CR_UNUSED(noarg);
    unsigned long len = 0;
    if (check_MetadataStatus(self))
        return NULL;
    GHashTable *ht = cr_metadata_hashtable(self->md);
    if (ht)
        len = (unsigned long) g_hash_table_size(ht);
    return PyLong_FromUnsignedLong(len);
}

/*
static PyObject *
ht_add(_MetadataObject *self, PyObject *args)
{
    char *key;
    PyObject *py_pkg;
    cr_Package *pkg;

    if (!PyArg_ParseTuple(args, "sO!:add", &key, &Package_Type, &pkg))
        return NULL;
    if (check_MetadataHashtableStatus(self))
        return NULL;

    pkg = Package_FromPyObject(pkg);
    if (!pkg)
        Py_RETURN_NONE;

    Py_XINCREF(py_pkg);
    // XXX: Store referenced object for Py_XDECREF!!!!!
    g_hash_table_replace(self->md->ht, key, pkg);
    Py_RETURN_NONE;
}
*/

static PyObject *
ht_has_key(_MetadataObject *self, PyObject *args)
{
    char *key;

    if (!PyArg_ParseTuple(args, "s:has_key", &key))
        return NULL;
    if (check_MetadataStatus(self))
        return NULL;

    if (g_hash_table_lookup(cr_metadata_hashtable(self->md), key))
        Py_RETURN_TRUE;
    Py_RETURN_FALSE;
}

static PyObject *
ht_keys(_MetadataObject *self, PyObject *args)
{
    CR_UNUSED(args);

    if (check_MetadataStatus(self))
        return NULL;

    GList *keys = g_hash_table_get_keys(cr_metadata_hashtable(self->md));
    PyObject *list = PyList_New(0);

    for (GList *elem = keys; elem; elem = g_list_next(elem)) {
        PyObject *py_str = PyString_FromString(elem->data);
        assert(py_str);
        if (PyList_Append(list, py_str) == -1) {
            Py_XDECREF(list);
            g_list_free(keys);
            return NULL;
        }
        Py_DECREF(py_str);
    }

    g_list_free(keys);
    return list;
}

static PyObject *
ht_remove(_MetadataObject *self, PyObject *args)
{
    char *key;

    if (!PyArg_ParseTuple(args, "s:del", &key))
        return NULL;
    if (check_MetadataStatus(self))
        return NULL;

    if (g_hash_table_remove(cr_metadata_hashtable(self->md), key))
        Py_RETURN_TRUE;
    Py_RETURN_FALSE;
}

static PyObject *
ht_get(_MetadataObject *self, PyObject *args)
{
    char *key;

    if (!PyArg_ParseTuple(args, "s:get", &key))
        return NULL;
    if (check_MetadataStatus(self))
        return NULL;

    cr_Package *pkg = g_hash_table_lookup(cr_metadata_hashtable(self->md), key);
    if (!pkg)
        Py_RETURN_NONE;
    return (Object_FromPackage_WithParent(pkg, 0, (PyObject *) self));
}

static struct PyMethodDef metadata_methods[] = {
    {"load_xml", (PyCFunction)load_xml, METH_VARARGS, NULL},
    {"locate_and_load_xml", (PyCFunction)locate_and_load_xml, METH_VARARGS, NULL},
    {"len",     (PyCFunction)ht_len, METH_NOARGS, NULL},
//    {"add",     (PyCFunction)ht_add, METH_VARARGS, NULL},
    {"has_key", (PyCFunction)ht_has_key, METH_VARARGS, NULL},
    {"keys",    (PyCFunction)ht_keys, METH_NOARGS, NULL},
    {"remove",  (PyCFunction)ht_remove, METH_VARARGS, NULL},
    {"get",     (PyCFunction)ht_get, METH_VARARGS, NULL},
    {NULL} /* sentinel */
};

/* Object */

PyTypeObject Metadata_Type = {
    PyObject_HEAD_INIT(NULL)
    0,                              /* ob_size */
    "createrepo_c.Metadata",        /* tp_name */
    sizeof(_MetadataObject),        /* tp_basicsize */
    0,                              /* tp_itemsize */
    (destructor)metadata_dealloc,   /* tp_dealloc */
    0,                              /* tp_print */
    0,                              /* tp_getattr */
    0,                              /* tp_setattr */
    0,                              /* tp_compare */
    (reprfunc)metadata_repr,        /* tp_repr */
    0,                              /* tp_as_number */
    0,                              /* tp_as_sequence */
    0,                              /* tp_as_mapping */
    0,                              /* tp_hash */
    0,                              /* tp_call */
    0,                              /* tp_str */
    0,                              /* tp_getattro */
    0,                              /* tp_setattro */
    0,                              /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT|Py_TPFLAGS_BASETYPE, /* tp_flags */
    "Metadata object",              /* tp_doc */
    0,                              /* tp_traverse */
    0,                              /* tp_clear */
    0,                              /* tp_richcompare */
    0,                              /* tp_weaklistoffset */
    PyObject_SelfIter,              /* tp_iter */
    0,                              /* tp_iternext */
    metadata_methods,               /* tp_methods */
    0,                              /* tp_members */
    metadata_getsetters,            /* tp_getset */
    0,                              /* tp_base */
    0,                              /* tp_dict */
    0,                              /* tp_descr_get */
    0,                              /* tp_descr_set */
    0,                              /* tp_dictoffset */
    (initproc)metadata_init,        /* tp_init */
    0,                              /* tp_alloc */
    metadata_new,                   /* tp_new */
    0,                              /* tp_free */
    0,                              /* tp_is_gc */
};
