#!/usr/bin/env python3
import sys
import os
import argparse
import glob
from Bio import AlignIO
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from Bio.Align import MultipleSeqAlignment
from Bio import SearchIO
# from Bio.Blast.Applications import NcbimakeblastdbCommandline deprecated!
# from Bio.Blast.Applications import NcbiblastnCommandline deprecated!
from io import StringIO
from shutil import copyfile
import statistics
import subprocess

def get_magOTUs_of_group(group_provided, ref_info):
    magOTU_list = []
    with open(ref_info, "r") as ref_info_fh:
        for line in ref_info_fh:
            line = line.strip()
            if line.startswith("ID"):
                header = line+"\n"
                continue
            genome_id = line.split("\t")[0]
            group_read = line.split("\t")[18]
            magOTU = line.split("\t")[11]
            if group_read == group_provided:
                if not magOTU in magOTU_list:
                    magOTU_list.append(magOTU)
            else:
                continue
    return(magOTU_list)

def magOTU_of_mag(mag, ref_info):
    with open(ref_info, "r") as ref_info_fh:
        for line in ref_info_fh:
            line = line.strip()
            if line.startswith("ID"):
                header = line+"\n"
                continue
            genome_id = line.split("\t")[0]
            magOTU = line.split("\t")[11]
            if mag == genome_id:
                return(magOTU)

def get_best_blast_hit(orf_file, db_file):
    process = subprocess.Popen(["blastn", "-db", db_file, "-query", orf_file, "-outfmt", 5, "-evalue", 0.001, "-perc_identity", 70],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True)
    stdout, stderr = process.communicate()
    blast_obj =  SearchIO.read(StringIO(stdout), "blast-xml")
    top_hit_genome = None
    if (len(blast_obj) != 0):
        top_hit_id = blast_obj[0].id
        split_hit_id = top_hit_id.split('_')
        top_hit_genome = split_hit_id[0]
    return(top_hit_genome)

def parse_MAG_name_from_gene_header(header):
    """
    read header with gene id in ffn files and get MAG name
    eg. MAG_C1.5_18 from '>MAG_C1.5_18_01186 hypothetical protein'
    it removes the final number after the underscore which goes from 1 to n
    where n is the gene id numbered by prokka
    """
    if ">" in header:
        parsed_header = "_".join(header.split(" ")[0].split(">")[1].split("_")[:-1])
    else:
        parsed_header = "_".join(header.split(" ")[0].split("_")[:-1])
    return(parsed_header)

def get_orf_max_perc_id_in_magOTU(ref_aln_file, orf_file, magOTU, ref_info):
    #Add orf to reference alignment with muscle
    process = subprocess.Popen(['muscle', '-profile', '-in1',ref_aln_file, '-in2', orf_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True)
    stdout, stderr = process.communicate()
    new_aln =  AlignIO.read(StringIO(stdout), "fasta")
    #Get seq-ids and corresponding seq-objects for the reference genomes and orf
    ref_aln_obj = AlignIO.read(ref_aln_file,"fasta")
    ref_aln_ids = [aln_record.id for aln_record in ref_aln_obj]
    all_seq_objects = dict()
    for aln_record in new_aln:
        all_seq_objects[aln_record.id]=aln_record
    orf_seq_obj = SeqIO.read(orf_file, "fasta")
    orf_length = len(orf_seq_obj.seq)
    orf_id = orf_seq_obj.id
    #Generate pairwise alignments by subsetting the new core alignment containing the orf. For each pairwise alignment, calculate the percentage identity. Save the maximum percentage id and corresponding reference genome id
    max_perc_id = 0
    max_perc_id_gene = None
    for ref_id_header in ref_aln_ids:
        ref_id = parse_MAG_name_from_gene_header(ref_id_header)
        if magOTU_of_mag(ref_id, ref_info) == magOTU: #Only align orf to core-seqs of the recruiting species
            sub_seq_objects = [all_seq_objects[ref_id], all_seq_objects[orf_id]]
            sub_aln = MultipleSeqAlignment(sub_seq_objects)
            sub_aln_perc_id = perc_id(sub_aln, orf_length)
            if (sub_aln_perc_id > max_perc_id and sub_aln_perc_id > 60):
                max_perc_id = sub_aln_perc_id
                max_perc_id_gene = ref_id
    return(orf_id, max_perc_id_gene, max_perc_id)

parser = argparse.ArgumentParser()
requiredNamed = parser.add_argument_group('required arguments')
requiredNamed.add_argument('--group', metavar="group", required=True, help="Name of genus or group that the script is being run for (historically, phylotype)", action="store")
requiredNamed.add_argument('--ref_info',metavar="ref_info",required=True, help="Info about MAG status with MAG name in first column and other information accroding to checkpoint output", action="store") # same as 06_MAG_binning/MAGs_filt_GenomeInfo_auto.tsv
requiredNamed.add_argument('--input_og_seq_dir', metavar="input_og_seq_dir", required=True, help="Path to directory containing *.ffn and *.aln_nuc.fasta files of single-copy orthologs", action="store")
requiredNamed.add_argument('--magOTU_seqs_dir_path', metavar="magOTU_seqs_dir_path", required=True, help="Path to store magOTU-wise seperated sequences (inside which magOTU_seqs_dir(s) exist)", action="store")
requiredNamed.add_argument('--orf_db', metavar="orf_db", required=True, help="File containing concatenated filtered metagenomic ORFs", action="store")
requiredNamed.add_argument('--perc_id_path', metavar="perc_id_path", required=True, help="Path to file to write percentage id results to", action="store")
requiredNamed.add_argument('--log_path', metavar="log_path", required=True, help="Path to store magOTU-wise seperated sequences (inside which magOTU_seqs_dir(s) exist)", action="store")


args = parser.parse_args()
group = args.group
ref_info = args.ref_info
input_og_seq_dir = args.input_og_seq_dir
magOTU_seqs_dir_path = args.magOTU_seqs_dir_path
orf_db = args.orf_db
perc_id_path = args.perc_id_path

log_path = args.log_path

if (os.stat(log_path).st_size != 0):
    log_fh = open(log_path, "a")
else:
    log_fh = open(log_path, "w")

magOTU_list = get_magOTUs_of_group(group, ref_info)

magOTU_seqs_dir_dict = {}

for magOTU in magOTU_list:
    print(f"Working on magOTU: {magOTU}")
    perc_id_file = os.path.join(perc_id_path, "_".join([group, magOTU, "perc_id.txt"]))
    with open(perc_id_file, "w") as perc_id_fh:
        header = "\t".join(["OG_group", "ORF_id","Gene_id","Perc_id","Closest_SDP"])
        perc_id_fh.write(f"{header}\n")
    magOTU_seqs_dir = os.path.join(magOTU_seqs_dir_path, magOTU)
    magOTU_seqs_dir_dict[magOTU] = magOTU_seqs_dir
    orf_file_suffix = "*_orfs.ffn"
    orf_files = glob.glob(os.path.join(magOTU_seqs_dir_path, orf_file_suffix))
    print(f"For {group} and magOTU {magOTU}, {len(orf_files)} OG groups were found")
    count_aln_results = 0
    count_magOTU_recruits = dict()
        # for now I consider all OGs regardless of whether they are present
        # in one magOTU exclusively or in all of them the result of this
        # will be that there will appear to be more ORFs specifically mapping
        # to it not because the OG is well suited to uniquely match the magOTU
        # but because it is simple not present elsewhere (missing genes in MAGs)
        # I assume for now that this will only be a minority of cases
    for orf_file in orf_files:
         print(f"Processing orf-file: {orf_file}")
         OG = os.path.basename(file).split("_orfs.ffn")[0]
         core_aln_file = os.path.join(input_og_seq_dir, OG + "_aln_nuc.fasta")
         core_ffn_file = os.path.join(input_og_seq_dir, OG + ".ffn")
         temp_ffn = os.path.join(input_og_seq_dir, "temp.ffn")
         temp_orf_ffn = os.path.join(input_og_seq_dir, "temp_orf.ffn")
         # temp_ffn = OG + "_temp.ffn"
         # temp_orf_ffn = OG + "_temp_orf.ffn"
         copyfile(core_ffn_file, os.path.join(magOTU_seqs_dir, temp_ffn))
         subprocess.run(["makeblastdb", "-in", temp_ffn, "-dbtype", "nucl"])
         for seq_record in SeqIO.parse(orf_file, "fasta"):
             SeqIO.write(seq_record, temp_orf_ffn, "fasta")
             blast_result = get_best_blast_hit(temp_orf_ffn, temp_ffn)
             if (blast_result == None): continue
             # we are only interested in the max perc id with the current magOTU
             aln_result = get_orf_max_perc_id_in_magOTU(core_aln_file, temp_orf_ffn, magOTU, ref_info)
