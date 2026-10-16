// Stream full-catalog replacements into disposable workspace DAT copies.
// This program has no operation for installing into a live game directory.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

internal static class FullNativeDat
{
    [DllImport("DatExport.dll",EntryPoint="OpenDatFileEx2",CallingConvention=CallingConvention.Cdecl)]
    internal static extern int Open(int h,string path,uint flags,out int master,out int block,out int vnum,out int game,out ulong fileId,StringBuilder stamp,StringBuilder guid);
    [DllImport("DatExport.dll",CallingConvention=CallingConvention.Cdecl)] internal static extern void CloseDatFile(int h);
    [DllImport("DatExport.dll",CallingConvention=CallingConvention.Cdecl)] internal static extern uint GetNumSubfiles(int h);
    [DllImport("DatExport.dll",CallingConvention=CallingConvention.Cdecl)] internal static extern void GetSubfileSizes(int h,out int did,out int size,out int iteration,int offset,int count);
    [DllImport("DatExport.dll",CallingConvention=CallingConvention.Cdecl)] internal static extern int GetSubfileVersion(int h,int did);
    [DllImport("DatExport.dll",CallingConvention=CallingConvention.Cdecl)] internal static extern int PurgeSubfileData(int h,int did);
    [DllImport("DatExport.dll",CallingConvention=CallingConvention.Cdecl)] internal static extern int PutSubfileData(int h,int did,IntPtr buffer,int offset,int size,int version,int iteration,bool compress);
    [DllImport("DatExport.dll",CallingConvention=CallingConvention.Cdecl)] internal static extern bool Flush(int h);
}

internal sealed class FullRecord
{
    internal int Id,Size,Version,Iteration;
    internal long Offset;
    internal byte[] Hash;
    internal bool Found;
}

internal static class FullDatPatchWorker
{
    static string HashFile(string path)
    {
        using(var file=File.OpenRead(path)) using(var hash=SHA256.Create())
            return BitConverter.ToString(hash.ComputeHash(file)).Replace("-","").ToLowerInvariant();
    }
    static void RequireHash(string path,string expected)
    {
        if(HashFile(path)!=expected)throw new InvalidDataException("File hash mismatch: "+Path.GetFileName(path));
    }
    static int Main(string[] args)
    {
        Console.OutputEncoding=new UTF8Encoding(false);
        try { Run(args);return 0; }
        catch(Exception error) { Console.Error.WriteLine(error);return 1; }
    }
    static void Run(string[] args)
    {
        if(args.Length!=4)throw new ArgumentException("<workspace-master-dat> <payload-pack> <original-dat-sha256> <pack-sha256>");
        string path=Path.GetFullPath(args[0]);
        string work=Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"..","work"))+Path.DirectorySeparatorChar;
        if(!path.StartsWith(work,StringComparison.OrdinalIgnoreCase))throw new InvalidOperationException("Writes restricted to this package's work directory");
        string name=Path.GetFileName(path);
        if(name!="client_local_English.dat" && name!="client_surface.dat" && name!="client_general.dat")throw new InvalidOperationException("Only complete archive-group masters can be patched");
        RequireHash(path,args[2]);RequireHash(args[1],args[3]);
        using(var stream=File.OpenRead(args[1])) using(var input=new BinaryReader(stream,Encoding.UTF8))
        {
            if(Encoding.ASCII.GetString(input.ReadBytes(8))!="LTZHPAK1")throw new InvalidDataException("Unknown payload pack format");
            uint count=input.ReadUInt32();
            if(count==0 || count>1000000)throw new InvalidDataException("Invalid payload count");
            var records=new List<FullRecord>();var index=new Dictionary<int,FullRecord>();
            for(uint i=0;i<count;i++)
            {
                var record=new FullRecord {Id=input.ReadInt32(),Size=input.ReadInt32(),Hash=input.ReadBytes(32)};
                if(record.Size<4 || record.Size>32*1024*1024 || record.Hash.Length!=32 || stream.Length-stream.Position<record.Size)
                    throw new InvalidDataException("Invalid/truncated payload");
                if(index.ContainsKey(record.Id))throw new InvalidDataException("Duplicate resource id");
                record.Offset=stream.Position;stream.Seek(record.Size,SeekOrigin.Current);
                records.Add(record);index.Add(record.Id,record);
            }
            if(stream.Position!=stream.Length)throw new InvalidDataException("Unexpected pack trailer");
            int master,block,vnum,game;ulong fileId;
            int opened=FullNativeDat.Open(0,path,130u,out master,out block,out vnum,out game,out fileId,new StringBuilder(64),new StringBuilder(64));
            if(opened!=0)throw new IOException("Native DAT open failed: "+opened);
            try
            {
                uint resources=FullNativeDat.GetNumSubfiles(0);
                for(int i=0;i<resources;i++)
                {
                    int did,size,iteration;FullNativeDat.GetSubfileSizes(0,out did,out size,out iteration,i,1);
                    FullRecord record;
                    if(index.TryGetValue(did,out record))
                    {
                        record.Version=FullNativeDat.GetSubfileVersion(0,did);record.Iteration=iteration;record.Found=true;
                    }
                }
                foreach(var record in records)if(!record.Found)throw new InvalidDataException("Replacement id absent: "+record.Id.ToString("X8"));
                int done=0;
                foreach(var record in records)
                {
                    stream.Position=record.Offset;byte[] data=input.ReadBytes(record.Size);
                    if(data.Length!=record.Size || BitConverter.ToInt32(data,0)!=record.Id)throw new InvalidDataException("Payload id/length mismatch");
                    using(var hash=SHA256.Create())
                        if(BitConverter.ToString(hash.ComputeHash(data))!=BitConverter.ToString(record.Hash))throw new InvalidDataException("Payload hash mismatch");
                    IntPtr buffer=Marshal.AllocHGlobal(data.Length);
                    try
                    {
                        Marshal.Copy(data,0,buffer,data.Length);
                        int purged=FullNativeDat.PurgeSubfileData(0,record.Id);
                        if(purged!=0)throw new IOException("Purge failed: "+purged);
                        int written=FullNativeDat.PutSubfileData(0,record.Id,buffer,0,data.Length,record.Version,record.Iteration,false);
                        if(written!=data.Length)throw new IOException("Write failed: "+written);
                    }
                    finally { Marshal.FreeHGlobal(buffer); }
                    done++;
                    if(done%5000==0 || done==records.Count)Console.WriteLine("Applied "+done+"/"+records.Count+" "+name);
                }
                if(!FullNativeDat.Flush(0))throw new IOException("DAT flush failed");
                Console.WriteLine("Flushed "+records.Count+" replacements in "+name);
            }
            finally { FullNativeDat.CloseDatFile(0); }
        }
    }
}
