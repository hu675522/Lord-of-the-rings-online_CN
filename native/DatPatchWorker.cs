// The native writer is restricted to disposable workspace copies. Installation
// and restoration use separately hash-verified full-file copies, not DLL writes.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;

internal static class NativeDat
{
    [DllImport("DatExport.dll", EntryPoint="OpenDatFileEx2", CallingConvention=CallingConvention.Cdecl)]
    internal static extern int Open(int handle, string path, uint flags, out int master, out int block, out int vnum, out int game,
        out ulong fileId, StringBuilder stamp, StringBuilder guid);
    [DllImport("DatExport.dll", CallingConvention=CallingConvention.Cdecl)] internal static extern void CloseDatFile(int h);
    [DllImport("DatExport.dll", CallingConvention=CallingConvention.Cdecl)] internal static extern uint GetNumSubfiles(int h);
    [DllImport("DatExport.dll", CallingConvention=CallingConvention.Cdecl)] internal static extern void GetSubfileSizes(int h, out int did, out int size, out int iteration, int offset, int count);
    [DllImport("DatExport.dll", CallingConvention=CallingConvention.Cdecl)] internal static extern int GetSubfileVersion(int h, int did);
    [DllImport("DatExport.dll", CallingConvention=CallingConvention.Cdecl)] internal static extern int PurgeSubfileData(int h, int did);
    [DllImport("DatExport.dll", CallingConvention=CallingConvention.Cdecl)] internal static extern int PutSubfileData(int h, int did, IntPtr buffer, int offset, int size, int version, int iteration, bool compress);
    [DllImport("DatExport.dll", CallingConvention=CallingConvention.Cdecl)] internal static extern bool Flush(int h);
}

internal static class DatPatchWorker
{
    static string Hash(string path)
    {
        using(var s=File.OpenRead(path)) using(var h=SHA256.Create()) return BitConverter.ToString(h.ComputeHash(s)).Replace("-", "").ToLowerInvariant();
    }
    static int Main(string[] args)
    {
        Console.OutputEncoding=new UTF8Encoding(false);
        try { Run(args); return 0; }
        catch(Exception e) { Console.Error.WriteLine(e.ToString()); return 1; }
    }
    static void Run(string[] args)
    {
        if(args.Length!=2 && args.Length!=3) throw new ArgumentException("probe <archive> | apply <workspace-archive> <manifest>");
        bool apply=args[0]=="apply";
        if(!apply && args[0]!="probe") throw new ArgumentException("Unknown command");
        string path=Path.GetFullPath(args[1]);
        Dictionary<string,object> manifest=null;
        if(apply)
        {
            if(args.Length!=3) throw new ArgumentException("Missing manifest");
            string work=Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"..","work"))+Path.DirectorySeparatorChar;
            if(!path.StartsWith(work,StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Native writes are restricted to client_patch/work");
            manifest=new JavaScriptSerializer{MaxJsonLength=16*1024*1024}.Deserialize<Dictionary<string,object>>(File.ReadAllText(args[2],Encoding.UTF8));
            if(Hash(path)!=Convert.ToString(manifest["archive_sha256"])) throw new InvalidOperationException("Workspace archive hash mismatch");
        }
        int master,block,vnum,game; ulong fileId;
        int opened=NativeDat.Open(0,path,apply?130u:134u,out master,out block,out vnum,out game,out fileId,new StringBuilder(64),new StringBuilder(64));
        if(opened!=0) throw new IOException("Native DAT open failed, returned "+opened);
        try
        {
            uint count=NativeDat.GetNumSubfiles(0);
            Console.WriteLine("Opened "+Path.GetFileName(path)+"; resources="+count+"; block="+block+"; vnum="+vnum);
            if(!apply) return;
            var records=(IEnumerable)manifest["records"];
            var required=new Dictionary<int,Dictionary<string,object>>();
            foreach(Dictionary<string,object> record in records) required.Add(Convert.ToInt32(record["id"]),record);
            var versions=new Dictionary<int,int>(); var iterations=new Dictionary<int,int>();
            for(int index=0;index<count;index++)
            {
                int did,size,iteration;
                NativeDat.GetSubfileSizes(0,out did,out size,out iteration,index,1);
                if(required.ContainsKey(did)) {versions.Add(did,NativeDat.GetSubfileVersion(0,did)); iterations.Add(did,iteration);}
            }
            if(versions.Count!=required.Count) throw new InvalidOperationException("A replacement resource does not exist in this archive");
            string manifestDir=Path.GetDirectoryName(Path.GetFullPath(args[2]));
            foreach(var pair in required)
            {
                int did=pair.Key;
                string payload=Path.GetFullPath(Path.Combine(manifestDir,Convert.ToString(pair.Value["file"])));
                if(!payload.StartsWith(manifestDir+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Payload escapes package directory");
                if(Hash(payload)!=Convert.ToString(pair.Value["sha256"])) throw new InvalidOperationException("Payload hash mismatch");
                byte[] data=File.ReadAllBytes(payload);
                if(data.Length<4 || BitConverter.ToInt32(data,0)!=did) throw new InvalidOperationException("Payload resource id mismatch");
                IntPtr buffer=Marshal.AllocHGlobal(data.Length);
                try
                {
                    Marshal.Copy(data,0,buffer,data.Length);
                    int purged=NativeDat.PurgeSubfileData(0,did);
                    if(purged!=0) throw new IOException("Resource purge failed "+did+": "+purged);
                    int written=NativeDat.PutSubfileData(0,did,buffer,0,data.Length,versions[did],iterations[did],false);
                    if(written!=data.Length) throw new IOException("Resource write failed "+did+": "+written);
                    Console.WriteLine("Replaced 0x"+did.ToString("X8")+"; bytes="+written);
                }
                finally {Marshal.FreeHGlobal(buffer);}
            }
            if(!NativeDat.Flush(0)) throw new IOException("DAT flush failed");
            Console.WriteLine("Flushed "+required.Count+" replacements");
        }
        finally {NativeDat.CloseDatFile(0);}
    }
}
