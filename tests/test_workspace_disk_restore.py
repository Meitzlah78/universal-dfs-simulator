import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np
import pandas as pd

import simmah_workspace_backup as backup


class DiskRestoreTest(unittest.TestCase):
    def payload(self, values):
        return dict(record=dict(id='dk',name='entries.csv',data='original'),
                    checkpoint=dict(values=values,uploads={},artifacts={}))

    def test_disk_restore_never_reads_the_whole_archive_or_npy_attachment(self):
        original=np.random.default_rng(83).integers(0,256,3_000_000,dtype=np.uint8)
        raw=backup.pack(self.payload(dict(outcomes=original)))
        read=zipfile.ZipFile.read
        reads=[]
        stream_read=zipfile.ZipExtFile.read
        def bounded(stream, size=-1):
            if str(stream.name).endswith('.npy'):
                self.assertGreaterEqual(size,0)
                self.assertLessEqual(size,backup.RESTORE_READ_BYTES)
                reads.append(size)
            return stream_read(stream,size)
        def metadata_only(bundle,name,*a,**kw):
            self.assertFalse(str(name).endswith('.npy'))
            return read(bundle,name,*a,**kw)
        with tempfile.TemporaryDirectory() as folder:
            ref=backup.write_backup('a'*32,raw,folder)
            with patch.object(Path,'read_bytes',side_effect=AssertionError('whole-file read')), \
                 patch.object(zipfile.ZipFile,'read',metadata_only), \
                 patch.object(zipfile.ZipExtFile,'read',bounded):
                result=backup.load_backup('a'*32,ref,folder)
        np.testing.assert_array_equal(result['checkpoint']['values']['outcomes'],original)
        self.assertGreaterEqual(reads.count(backup.RESTORE_READ_BYTES),2)

    def test_layout_dtype_empty_scalar_and_repeated_arrays_preserve_values(self):
        values=dict(c=np.arange(24,dtype='>i4').reshape(4,6),
                    f=np.asfortranarray(np.arange(24.).reshape(4,6)),
                    scalar=np.array(3.5),empty=np.empty((0,3)),
                    structured=np.array([(3,2.5)],dtype=[('id','i4'),('score','f8')]))
        values['repeat']=values['f']
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'backup.zip';path.write_bytes(backup.pack(self.payload(values)))
            restored=backup.unpack_file(path)['checkpoint']['values']
        for key,value in values.items():
            np.testing.assert_array_equal(restored[key],value)
            self.assertEqual(restored[key].dtype,value.dtype)
        self.assertTrue(restored['f'].flags.f_contiguous)
        restored['repeat'][0,0]=999
        self.assertNotEqual(restored['f'][0,0],999)  # Preserve independent decoded copies.

    def test_file_restore_preserves_typed_dataframe_and_uploads(self):
        values=dict(frame=pd.DataFrame({'name':['A','B'],
            'salary':pd.Series([5000,None],dtype='Int64')}),raw=b'original bytes')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'backup.zip';path.write_bytes(backup.pack(self.payload(values)))
            restored=backup.unpack_file(path)['checkpoint']['values']
        pd.testing.assert_frame_equal(restored['frame'],values['frame'])
        self.assertEqual(restored['raw'],values['raw'])

    def test_archive_hash_and_size_fail_before_array_allocation(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'backup.zip';path.write_bytes(backup.pack(self.payload(dict(x=np.arange(10)))))
            with patch.object(np,'empty',side_effect=AssertionError('allocated before verification')):
                with self.assertRaisesRegex(ValueError,'verification'):
                    backup.unpack_file(path,expected_digest='0'*64)
                with self.assertRaisesRegex(ValueError,'verification'):
                    backup.unpack_file(path,expected_bytes=1)

    def rewrite_array(self, raw, modify, rename=False):
        out=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw)) as source:
            data={name:source.read(name) for name in source.namelist()}
        name=next(name for name in data if name.endswith('.npy'))
        changed=modify(data[name])
        if rename:
            new_name=backup.digest(changed)+'.npy'
            data['manifest.json']=data['manifest.json'].replace(name.encode(),new_name.encode())
            del data[name];name=new_name
        data[name]=changed
        with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as result:
            for name,value in data.items():result.writestr(name,value)
        return out.getvalue()

    def test_attachment_hash_corruption_rejected_with_valid_zip_crc(self):
        raw=backup.pack(self.payload(dict(x=np.arange(10))))
        raw=self.rewrite_array(raw,lambda content:content[:-1]+bytes([content[-1]^1]))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.zip';path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'attachment failed verification'):
                backup.unpack_file(path)

    def test_forged_npy_shape_fails_before_allocating(self):
        raw=backup.pack(self.payload(dict(x=np.arange(10))))
        def forged(content):
            stream=io.BytesIO()
            np.lib.format.write_array_header_1_0(stream,
                dict(descr='<f8',fortran_order=False,shape=(10**12,)))
            return stream.getvalue()+b'123'
        raw=self.rewrite_array(raw,forged,rename=True)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.zip';path.write_bytes(raw)
            with patch.object(np,'empty',side_effect=AssertionError('untrusted allocation')):
                with self.assertRaisesRegex(ValueError,'array dimensions'):
                    backup.unpack_file(path)


if __name__=='__main__':unittest.main()
